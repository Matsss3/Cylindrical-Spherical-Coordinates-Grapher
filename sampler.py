"""Sampling utilities for the grapher.

This module turns parsed equations into numerical grids that can be rendered.
It supports three main modes:

- Explicit surfaces in Cartesian, cylindrical, and spherical coordinates
- Explicit parametric curves
- Implicit scalar fields for later zero-isosurface extraction

The sampler does not plot anything. It only evaluates equations on grids.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

import numpy as np
import sympy as sp
from numpy.typing import NDArray
from sympy.utilities.lambdify import lambdify

from parser import CoordinateSystem, ParsedEquation
from transform import cylindrical_to_cartesian, spherical_to_cartesian


@dataclass(frozen=True)
class ExplicitSurfaceSample:
    """A sampled explicit surface in Cartesian space."""

    x: NDArray[np.floating]
    y: NDArray[np.floating]
    z: NDArray[np.floating]
    parameter_a: NDArray[np.floating]
    parameter_b: NDArray[np.floating]


@dataclass(frozen=True)
class CurveSample:
    """A sampled curve in Cartesian space."""

    x: NDArray[np.floating]
    y: NDArray[np.floating]
    z: NDArray[np.floating]
    parameter: NDArray[np.floating]


@dataclass(frozen=True)
class ImplicitFieldSample:
    """A sampled scalar field for implicit surface extraction."""

    x: NDArray[np.floating]
    y: NDArray[np.floating]
    z: NDArray[np.floating]
    values: NDArray[np.floating]


@dataclass(frozen=True)
class SampleResult:
    """Unified output from the sampler."""

    mode: str
    explicit_surface: Optional[ExplicitSurfaceSample] = None
    curve: Optional[CurveSample] = None
    implicit_field: Optional[ImplicitFieldSample] = None


_DEFAULT_RANGES: Dict[str, Tuple[float, float]] = {
    "x": (-5.0, 5.0),
    "y": (-5.0, 5.0),
    "z": (-5.0, 5.0),
    "r": (0.0, 10.0),
    "theta": (0.0, 2.0 * np.pi),
    "phi": (0.0, np.pi),
    "rho": (0.0, 10.0),
    "t": (-10.0, 10.0),
}

_IMPLICIT_RANGES: Dict[str, Tuple[float, float]] = {
    "x": (-10.0, 10.0),
    "y": (-10.0, 10.0),
    "z": (-10.0, 10.0),
    "r": (-10.0, 10.0),
    "theta": (-2.0 * np.pi, 2.0 * np.pi),
    "phi": (-2.0 * np.pi, 2.0 * np.pi),
    "rho": (-10.0, 10.0),
    "t": (-10.0, 10.0),
}

def _linspace_for(name: str, points: int, ranges: Optional[Dict[str, Tuple[float, float]]] = None) -> NDArray[np.floating]:
    """Build a 1D sampling grid for a variable name."""

    source = ranges or _DEFAULT_RANGES
    if name not in source:
        raise ValueError(f"No range configured for variable {name!r}")
    start, stop = source[name]
    return np.linspace(float(start), float(stop), int(points), dtype=float)


def _build_lambdified(expression: sp.Expr, symbols: Tuple[sp.Symbol, ...]) -> Callable:
    """Create a NumPy-backed function from a SymPy expression."""

    return lambdify(symbols, expression, modules="numpy")


def sample_explicit_surface(
    parsed: ParsedEquation,
    resolution: int = 100,
    ranges: Optional[Dict[str, Tuple[float, float]]] = None,
) -> ExplicitSurfaceSample:
    """Sample an explicit surface described by a ParsedEquation.

    The equation should be one where a dependent variable is isolated on one side,
    such as z = f(x, y), z = f(r, theta), or rho = f(theta, phi).
    """

    if not parsed.is_explicit or parsed.dependent_variable is None:
        raise ValueError("Explicit surface sampling requires an explicit equation.")

    dep = parsed.dependent_variable
    indep1, indep2 = parsed.independent_variables
    system = parsed.coordinate_system
    res = int(resolution)

    a = _linspace_for(indep1.name, res, ranges)
    b = _linspace_for(indep2.name, res, ranges)

    A, B = np.meshgrid(a, b)

    func = _build_lambdified(parsed.rhs, (sp.Symbol(indep1.name), sp.Symbol(indep2.name)))
    C = np.asarray(func(A, B), dtype=float)
    if C.ndim == 0:
        C = np.full_like(A, C, dtype=float)
    match system:
        case CoordinateSystem.CARTESIAN:
            values = {dep.name: C, indep1.name: A, indep2.name: B}
            a_i, b_i, c_i = values["x"], values["y"], values["z"]
            return ExplicitSurfaceSample(x=a_i, y=b_i, z=c_i, parameter_a=A, parameter_b=B)
        case CoordinateSystem.CYLINDRICAL:
            values = {dep.name: C, indep1.name: A, indep2.name: B}
            a_i, b_i, c_i = values["r"], values["theta"], values["z"]
            cart = cylindrical_to_cartesian(a_i, b_i, c_i)
        case CoordinateSystem.SPHERICAL:
            values = {dep.name: C, indep1.name: A, indep2.name: B}
            a_i, b_i, c_i = values["rho"], values["theta"], values["phi"]
            cart = spherical_to_cartesian(a_i, b_i, c_i)
    return ExplicitSurfaceSample(x=cart.x, y=cart.y, z=cart.z, parameter_a=A, parameter_b=B)


def sample_curve(
    expression: ParsedEquation,
    resolution: int = 400,
    ranges: Optional[Dict[str, Tuple[float, float]]] = None,
) -> CurveSample:
    """Sample a parametric curve.

    The curve is expected to use the variable t as its parameter.
    This function supports the simplest useful version first: a curve encoded
    as one dependent variable in terms of t.

    Examples:
        x = cos(t)
        r = 2 + cos(t)
        rho = 1 + sin(t)
    """

    if not expression.is_explicit or expression.dependent_variable is None:
        raise ValueError("Curve sampling currently expects an explicit equation.")

    t = _linspace_for("t", resolution, ranges)

    system = expression.coordinate_system
    dep = expression.dependent_variable.name
    func = _build_lambdified(expression.rhs, (sp.Symbol("t"),))
    values = np.asarray(func(t), dtype=float)

    if system == CoordinateSystem.CARTESIAN:
        if dep == "x":
            return CurveSample(x=values, y=np.zeros_like(values), z=np.zeros_like(values), parameter=t)
        if dep == "y":
            return CurveSample(x=np.zeros_like(values), y=values, z=np.zeros_like(values), parameter=t)
        if dep == "z":
            return CurveSample(x=np.zeros_like(values), y=np.zeros_like(values), z=values, parameter=t)
        raise ValueError("Cartesian curve sampling expects x, y, or z as the dependent variable.")

    if system == CoordinateSystem.CYLINDRICAL:
        if dep == "r":
            cart = cylindrical_to_cartesian(values, t, np.zeros_like(values))
            return CurveSample(x=cart.x, y=cart.y, z=cart.z, parameter=t)
        if dep == "z":
            cart = cylindrical_to_cartesian(np.ones_like(values), t, values)
            return CurveSample(x=cart.x, y=cart.y, z=cart.z, parameter=t)
        raise ValueError("Cylindrical curve sampling expects r or z as the dependent variable.")

    if system == CoordinateSystem.SPHERICAL:
        if dep == "rho":
            cart = spherical_to_cartesian(values, t, np.full_like(values, np.pi / 2.0))
            return CurveSample(x=cart.x, y=cart.y, z=cart.z, parameter=t)
        raise ValueError("Spherical curve sampling expects rho as the dependent variable.")

    raise ValueError(f"Unsupported coordinate system: {system!r}")


def sample_implicit_field(
    parsed: ParsedEquation,
    resolution: int = 40,
    ranges: Optional[Dict[str, Tuple[float, float]]] = None,
) -> ImplicitFieldSample:
    """Sample an implicit equation as a scalar field.

    The returned values array is the residual of the equation. A later step can
    apply marching cubes or a similar isosurface algorithm to extract the zero
    level set.
    """

    system = parsed.coordinate_system
    res = int(resolution)

    if system == CoordinateSystem.CARTESIAN:
        x = _linspace_for("x", res, ranges)
        y = _linspace_for("y", res, ranges)
        z = _linspace_for("z", res, ranges)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        func = _build_lambdified(parsed.residual, (sp.Symbol("x"), sp.Symbol("y"), sp.Symbol("z")))
        values = np.asarray(func(X, Y, Z), dtype=float)
        return ImplicitFieldSample(x=X, y=Y, z=Z, values=values)

    if system == CoordinateSystem.CYLINDRICAL:
        r = _linspace_for("r", res, _IMPLICIT_RANGES)
        theta = _linspace_for("theta", res, _IMPLICIT_RANGES)
        z = _linspace_for("z", res, _IMPLICIT_RANGES)
        X, Y, Z = np.meshgrid(r, theta, z, indexing="ij")
        R = np.sqrt(X**2 + Y**2)
        T = np.arctan2(Y, X)
        func = _build_lambdified(parsed.residual, (sp.Symbol("r"), sp.Symbol("theta"), sp.Symbol("z")))
        values = np.asarray(func(R, T, Z), dtype=float)
        cart = cylindrical_to_cartesian(R, T, Z)
        return ImplicitFieldSample(x=cart.x, y=cart.y, z=cart.z, values=values)

    if system == CoordinateSystem.SPHERICAL:
        rho = _linspace_for("rho", res, _IMPLICIT_RANGES)
        theta = _linspace_for("theta", res, _IMPLICIT_RANGES)
        phi = _linspace_for("phi", res, _IMPLICIT_RANGES)
        X, Y, Z = np.meshgrid(rho, theta, phi, indexing="ij")
        RHO = np.sqrt(X**2 + Y**2 + Z**2)
        T = np.arctan2(Y, X)
        P = np.arccos(
            np.clip(
                np.divide(
                    Z,
                    RHO,
                    out=np.ones_like(RHO),
                    where=RHO > 0
                ),
                -1.0,
                1.0
            )
        )
        func = _build_lambdified(parsed.residual, (sp.Symbol("rho"), sp.Symbol("theta"), sp.Symbol("phi")))
        values = np.asarray(func(RHO, T, P), dtype=float)
        cart = spherical_to_cartesian(RHO, T, P)
        return ImplicitFieldSample(x=cart.x, y=cart.y, z=cart.z, values=values)

    raise ValueError(f"Unsupported coordinate system: {system!r}")


def sample_equation(
    parsed: ParsedEquation,
    resolution: int = 100,
    ranges: Optional[Dict[str, Tuple[float, float]]] = None,
    implicit_resolution: int = 40,
) -> SampleResult:
    """Dispatch to the appropriate sampling strategy for a parsed equation."""

    if parsed.is_explicit and parsed.dependent_variable is not None:
        dep = parsed.dependent_variable.name
        if dep == "t":
            curve = sample_curve(parsed, resolution=resolution, ranges=ranges)
            return SampleResult(mode="curve", curve=curve)
        surface = sample_explicit_surface(parsed, resolution=resolution, ranges=ranges)
        return SampleResult(mode="explicit_surface", explicit_surface=surface)

    field = sample_implicit_field(parsed, resolution=implicit_resolution, ranges=ranges)
    return SampleResult(mode="implicit_field", implicit_field=field)


def default_ranges() -> Dict[str, Tuple[float, float]]:
    """Return a copy of the default sampling ranges."""

    return dict(_DEFAULT_RANGES)


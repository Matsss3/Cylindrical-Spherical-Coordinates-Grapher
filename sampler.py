"""Sampling utilities for the grapher.

This module turns parsed equations into numerical grids that can be rendered.
It supports three main modes:

- Explicit surfaces in Cartesian, cylindrical, and spherical coordinates
- Explicit parametric curves
- Implicit scalar fields for later zero-isosurface extraction
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

import numpy as np
import sympy as sp
from numpy.typing import NDArray
from sympy.utilities.lambdify import lambdify

from parser import CoordinateSystem, ParsedCurve, ParsedEquation
from timing import timer
from transform import cylindrical_to_cartesian, spherical_to_cartesian
from validation import InternalParseException, ParseException


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
    "varphi": (0.0, np.pi),
    "rho": (0.0, 10.0),
    "t": (-10.0, 10.0),
}

_IMPLICIT_RANGES: Dict[str, Tuple[float, float]] = {
    "x": (-10.0, 10.0),
    "y": (-10.0, 10.0),
    "z": (-10.0, 10.0),
    "r": (-10.0, 10.0),
    "theta": (-2.0 * np.pi, 2.0 * np.pi),
    "varphi": (-2.0 * np.pi, 2.0 * np.pi),
    "rho": (-10.0, 10.0),
    "t": (-10.0, 10.0),
}

def _linspace_for(name: str, points: int, ranges: Optional[Dict[str, Tuple[float, float]]] = None) -> NDArray[np.floating]:
    """Build a 1D sampling grid for a variable name."""

    source = ranges or _DEFAULT_RANGES
    if name not in source:
        print_name = f"\\(\\{name!r}\\)" if len(name) > 1 else f"\\({name!r}\\)"
        raise InternalParseException(f"No hay un rango configurado para la variable {print_name}.")
    start, stop = source[name]
    return np.linspace(float(start), float(stop), int(points), dtype=np.float32)


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
        raise InternalParseException("El muestreo de superficies explicitas requiere una ecuación explícita.")

    dep = parsed.dependent_variable
    indep1, indep2 = parsed.independent_variables
    system = parsed.coordinate_system
    res = int(resolution)

    if parsed.lhs == dep:
        expression = parsed.rhs
    elif parsed.rhs == dep:
        expression = parsed.lhs
    else:
        raise InternalParseException("No se encontró una expresión lambdificable para esta ecuación explícita.")

    a = _linspace_for(indep1.name, res, ranges)
    b = _linspace_for(indep2.name, res, ranges)

    A, B = np.meshgrid(a, b)

    func = _build_lambdified(expression, (sp.Symbol(indep1.name), sp.Symbol(indep2.name)))
    try:
        with np.errstate(
            over="raise",
            divide="raise",
            invalid="raise",
            under="ignore",
        ):
            C = np.asarray(func(A, B), dtype=np.float32)
    except Exception:
        raise ParseException("La expresión produce valores demasiado grandes.")

    if not np.isfinite(C).any():
        raise ParseException("La expresión no se puede evaluar.")

    if C.ndim == 0:
        C = np.full_like(A, C, dtype=np.float32)
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
            a_i, b_i, c_i = values["rho"], values["theta"], values["varphi"]
            cart = spherical_to_cartesian(a_i, b_i, c_i)
    return ExplicitSurfaceSample(x=cart.x, y=cart.y, z=cart.z, parameter_a=A, parameter_b=B)


def sample_curve(
    expression: ParsedCurve,
    resolution: int = 100,
    ranges: Optional[Dict[str, Tuple[float, float]]] = None,
) -> CurveSample:
    """Sample a parametric vectorial curve.

    The curve is expected to use the variable t as its parameter.
    """

    t = _linspace_for("t", resolution, ranges)
    system = expression.coordinate_system

    f = _build_lambdified(expression.x_expr, (sp.Symbol("t"),))
    g = _build_lambdified(expression.y_expr, (sp.Symbol("t"),))
    h = _build_lambdified(expression.z_expr, (sp.Symbol("t"),))


    try:
        with np.errstate(
            over="raise",
            divide="raise",
            invalid="raise",
            under="ignore",
        ):
            A = f(t)
            B = g(t)
            C = h(t)
    except Exception:
        raise ParseException("La expresión produce valores demasiado grandes.")

    if (
        not np.isfinite(A).any() or
        not np.isfinite(B).any() or
        not np.isfinite(C).any()
    ):
        raise ParseException("La expresión no se puede evaluar.")

    ref = next(
        (x for x in (A, B, C) if isinstance(x, np.ndarray)),
        None
    )

    if ref is None:
        raise ParseException("La curva debe estar parametrizada en función a \\(t\\).")

    if type(A) == int:
        A = np.full_like(ref, A, dtype=np.float32)
    if type(B) == int:
        B = np.full_like(ref, B, dtype=np.float32)
    if type(C) == int:
        C = np.full_like(ref, C, dtype=np.float32)

    match system:
        case CoordinateSystem.CARTESIAN:
            return CurveSample(x=A, y=B, z=C, parameter=t)
        case CoordinateSystem.CYLINDRICAL:
            cart = cylindrical_to_cartesian(A, B, C)
        case CoordinateSystem.SPHERICAL:
            cart = spherical_to_cartesian(A, B, C)
    return CurveSample(x=cart.x, y=cart.y, z=cart.z, parameter=t)


def sample_implicit_field(
    parsed: ParsedEquation,
    resolution: int = 40,
    ranges: Optional[Dict[str, Tuple[float, float]]] = None,
) -> ImplicitFieldSample:
    """Sample an implicit equation as a scalar field.

    The returned values array is the residual of the equation."""

    system = parsed.coordinate_system
    res = int(resolution)

    if system == CoordinateSystem.CARTESIAN:
        x = _linspace_for("x", res, ranges)
        y = _linspace_for("y", res, ranges)
        z = _linspace_for("z", res, ranges)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        func = _build_lambdified(parsed.residual, (sp.Symbol("x"), sp.Symbol("y"), sp.Symbol("z")))
        try:
            with np.errstate(
                over="raise",
                divide="raise",
                invalid="raise",
                under="ignore",
            ):
                values = np.asarray(func(X, Y, Z), dtype=np.float32)
        except Exception:
            raise ParseException("La expresión produce valores demasiado grandes.")
        if not np.isfinite(values).any():
            raise ParseException("La expresión no se puede evaluar.")
        return ImplicitFieldSample(x=X, y=Y, z=Z, values=values)

    if system == CoordinateSystem.CYLINDRICAL:
        r = _linspace_for("r", res, _IMPLICIT_RANGES)
        theta = _linspace_for("theta", res, _IMPLICIT_RANGES)
        z = _linspace_for("z", res, _IMPLICIT_RANGES)
        X, Y, Z = np.meshgrid(r, theta, z, indexing="ij")
        R = np.sqrt(X**2 + Y**2)
        T = np.arctan2(Y, X)
        func = _build_lambdified(parsed.residual, (sp.Symbol("r"), sp.Symbol("theta"), sp.Symbol("z")))
        try:
            with np.errstate(
                over="raise",
                divide="raise",
                invalid="raise",
                under="ignore",
            ):
                values = np.asarray(func(R, T, Z), dtype=np.float32)
        except Exception:
            raise ParseException("La expresión produce valores demasiado grandes.")
        if not np.isfinite(values).any():
            raise ParseException("La expresión no se puede evaluar.")
        cart = cylindrical_to_cartesian(R, T, Z)
        return ImplicitFieldSample(x=cart.x, y=cart.y, z=cart.z, values=values)

    if system == CoordinateSystem.SPHERICAL:
        rho = _linspace_for("rho", res, _IMPLICIT_RANGES)
        theta = _linspace_for("theta", res, _IMPLICIT_RANGES)
        phi = _linspace_for("varphi", res, _IMPLICIT_RANGES)
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
        func = _build_lambdified(parsed.residual, (sp.Symbol("rho"), sp.Symbol("theta"), sp.Symbol("varphi")))
        try:
            with np.errstate(
                over="raise",
                divide="raise",
                invalid="raise",
                under="ignore",
            ):
                values = np.asarray(func(RHO, T, P), dtype=np.float32)
        except Exception:
            raise ParseException("La expresión produce valores demasiado grandes.")
        if not np.isfinite(values).any():
            raise ParseException("La expresión no se puede evaluar.")
        cart = spherical_to_cartesian(RHO, T, P)
        return ImplicitFieldSample(x=cart.x, y=cart.y, z=cart.z, values=values)

    raise InternalParseException(f"Sistema coordinado no admitido: {system!r}")


def sample_equation(
    parsed_equation: Optional[ParsedEquation] = None,
    parsed_curve: Optional[ParsedCurve] = None,
    resolution: int = 100,
    ranges: Optional[Dict[str, Tuple[float, float]]] = None,
    implicit_resolution: int = 40,
) -> SampleResult:
    """Dispatch to the appropriate sampling strategy for a parsed equation."""

    if parsed_equation:
        if parsed_equation.is_explicit and parsed_equation.dependent_variable is not None:
            surface = sample_explicit_surface(parsed_equation, resolution=resolution, ranges=ranges)
            return SampleResult(mode="explicit_surface", explicit_surface=surface)
        field = sample_implicit_field(parsed_equation, resolution=implicit_resolution, ranges=ranges)
        return SampleResult(mode="implicit_field", implicit_field=field)
    elif parsed_curve:
        curve = sample_curve(parsed_curve, resolution=resolution, ranges=ranges)
        return SampleResult(mode="curve", curve=curve)
    else:
        raise InternalParseException("No se encontró una expresión adecuada para muestrear.")

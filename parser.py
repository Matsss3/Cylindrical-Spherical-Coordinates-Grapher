"""Equation parsing utilities for a coordinate-system grapher.

This module turns a LaTex expression into a structured form that later
modules can sample and render.

Supported equation styles:

1. Explicit surfaces / curves
   - Cartesian:      z = x^2 + y^2
   - Cylindrical:    z = r^2
   - Spherical:      rho = 2 + sin(phi)

2. Implicit equations
   - Cartesian:      x^2 + y^2 + z^2 = 1
   - Cylindrical:    r^2 + z^2 = 4
   - Spherical:      rho = 2

The parser does not solve the equation. It only normalizes it into SymPy
expressions and metadata that the sampler/renderer can consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Tuple

import sympy as sp
from latex2sympy2_extended import latex2sympy

class CoordinateSystem(str, Enum):
    """Supported coordinate systems for the grapher."""

    CARTESIAN = "cartesian"
    CYLINDRICAL = "cylindrical"
    SPHERICAL = "spherical"


@dataclass(frozen=True)
class ParsedEquation:
    """Normalized representation of a LaTeX equation."""

    original: str
    coordinate_system: CoordinateSystem
    lhs: sp.Expr
    rhs: sp.Expr
    residual: sp.Expr
    is_explicit: bool
    dependent_variable: Optional[sp.Symbol]
    independent_variables: Tuple[sp.Symbol, ...]

@dataclass(frozen=True)
class ParsedCurve:
    """Normalized representation of a user-entered parametric curve."""

    coordinate_system: CoordinateSystem
    x_expr: sp.Expr
    y_expr: sp.Expr
    z_expr: sp.Expr

def _parse_latex(expression: str) -> sp.Expr:
    """ Convert LaTeX expression string to sympy string. """
    return latex2sympy(expression)


def _symbols_for_system(system: CoordinateSystem) -> Mapping[str, sp.Symbol]:
    """Return the allowed symbols for a given coordinate system."""

    base = {
        "x": sp.Symbol("x", real=True),
        "y": sp.Symbol("y", real=True),
        "z": sp.Symbol("z", real=True),
        "r": sp.Symbol("r", nonnegative=True, real=True),
        "theta": sp.Symbol("theta", real=True),
        "phi": sp.Symbol("phi", real=True),
        "rho": sp.Symbol("rho", nonnegative=True, real=True),
        "t": sp.Symbol("t", real=True),
    }

    if system == CoordinateSystem.CARTESIAN:
        return {k: base[k] for k in ("x", "y", "z", "t")}
    if system == CoordinateSystem.CYLINDRICAL:
        return {k: base[k] for k in ("r", "theta", "z", "t")}
    if system == CoordinateSystem.SPHERICAL:
        return {k: base[k] for k in ("rho", "theta", "phi", "t")}


def _split_equation(expression: str) -> Tuple[str, str, bool]:
    """Split on one '=' if present.

    Returns
    -------
    lhs, rhs, explicit
        If no '=' is present, the whole expression is treated as an implicit
        equation equal to zero.
    """

    if "=" not in expression:
        return expression, "0", False

    parts = expression.split("=")
    if len(parts) != 2:
        raise ValueError("Only a single '=' is supported in one equation.")

    lhs, rhs = (part.strip() for part in parts)
    if not lhs or not rhs:
        raise ValueError("Both sides of the equation must be non-empty.")
    return lhs, rhs, True

def _split_curve(expression: str) -> Tuple[str, str, str]:
    """Split on commas if present.

    Returns
    -------
    x_expr, y_expr, z_expr
    """

    if expression.startswith("\\left(") and expression.endswith("\\right)"):
        expression = expression[6:-7]
    else:
        raise ValueError("Wrong curve syntax.")

    parts = []
    current = []
    depth = 0

    for ch in expression:
        if ch == ',' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        current.append(ch)

    parts.append(''.join(current).strip())

    if len(parts) != 3:
        raise ValueError("Expected exactly 3 components")

    return tuple(parts)


def _detect_dependent_variable(
    lhs: sp.Expr,
    rhs: sp.Expr,
    system: CoordinateSystem,
    symbols: Mapping[str, sp.Symbol],
) -> Optional[sp.Symbol]:
    """
    Detect equations of the form

        variable = expression

    where the variable belongs to the current coordinate system.
    """

    if system == CoordinateSystem.CARTESIAN:
        candidates = (
            symbols["x"],
            symbols["y"],
            symbols["z"],
        )

    elif system == CoordinateSystem.CYLINDRICAL:
        candidates = (
            symbols["r"],
            symbols["theta"],
            symbols["z"],
        )

    elif system == CoordinateSystem.SPHERICAL:
        candidates = (
            symbols["rho"],
            symbols["theta"],
            symbols["phi"],
        )

    for candidate in candidates:
        # candidate = expression
        if lhs == candidate and candidate not in rhs.free_symbols:
            return candidate

        # expression = candidate
        if rhs == candidate and candidate not in lhs.free_symbols:
            return candidate

    return None

def canonicalize(expr: sp.Expr, symbol_table: Mapping[str, sp.Symbol]) -> sp.Expr:
    """ Fix symbol types from LaTeX to reals by mapping """
    replacements = {
        s: symbol_table[s.name]
        for s in expr.free_symbols
        if s.name in symbol_table
    }

    return expr.xreplace(replacements)


def parse_equation(expression: str, coordinate_system: CoordinateSystem) -> ParsedEquation:
    """Parse and normalize a graphed equation.

    Parameters
    ----------
    expression:
        LaTeX equation string.
    coordinate_system:
        The coordinate system the user intends to work in.

    Returns
    -------
    ParsedEquation
        Structured equation metadata and SymPy expressions.
    """

    if not expression or not expression.strip():
        raise ValueError("Equation cannot be empty.")

    symbol_table = _symbols_for_system(coordinate_system)

    lhs_text, rhs_text, explicit = _split_equation(expression)
    lhs = canonicalize(_parse_latex(lhs_text), symbol_table)
    rhs = canonicalize(_parse_latex(rhs_text), symbol_table)

    residual = sp.simplify(lhs - rhs)
    dependent_variable = _detect_dependent_variable(lhs, rhs, coordinate_system, symbol_table)

    if coordinate_system == CoordinateSystem.CARTESIAN:
        all_vars = (symbol_table["x"], symbol_table["y"], symbol_table["z"])

    elif coordinate_system == CoordinateSystem.CYLINDRICAL:
        all_vars = (symbol_table["r"], symbol_table["theta"], symbol_table["z"])

    elif coordinate_system == CoordinateSystem.SPHERICAL:
        all_vars = (symbol_table["rho"], symbol_table["theta"], symbol_table["phi"])

    if dependent_variable is not None:
        independent_variables = tuple(
            v for v in all_vars
            if v != dependent_variable
        )
    else:
        independent_variables = tuple(
            sorted(
                lhs.free_symbols | rhs.free_symbols,
                key=lambda s: s.name
            )
        )

    return ParsedEquation(
        original=expression,
        coordinate_system=coordinate_system,
        lhs=lhs,
        rhs=rhs,
        residual=residual,
        is_explicit=explicit,
        dependent_variable=dependent_variable,
        independent_variables=independent_variables,
    )

def parse_curve(expression: str, coordinate_system: CoordinateSystem) -> ParsedCurve:
    """Parse and normalize a graphed curve.

    Parameters
    ----------
    expression:
        LaTeX curve parametric vectorial equation.
    coordinate_system:
        The coordinate system the user intends to work in.

    Returns
    -------
    ParsedCurve
        Structured equation metadata and SymPy expressions.
    """

    if not expression or not expression.strip():
        raise ValueError("Equation cannot be empty.")

    symbol_table = _symbols_for_system(coordinate_system)
    x_expr, y_expr, z_expr = _split_curve(expression)

    x_expr = canonicalize(_parse_latex(x_expr), symbol_table)
    y_expr = canonicalize(_parse_latex(y_expr), symbol_table)
    z_expr = canonicalize(_parse_latex(z_expr), symbol_table)

    return ParsedCurve(
        coordinate_system=coordinate_system,
        x_expr=x_expr,
        y_expr=y_expr,
        z_expr=z_expr
    )

def parse_equation_text(expression: str, coordinate_system: str) -> ParsedEquation:
    """Convenience wrapper that accepts a coordinate-system string."""

    try:
        system = CoordinateSystem(coordinate_system.lower().strip())
    except Exception as exc:
        raise ValueError(
            f"Unknown coordinate system {coordinate_system!r}. "
            f"Expected one of: {', '.join(s.value for s in CoordinateSystem)}"
        ) from exc

    return parse_equation(expression, system)


def parse_curve_text(expression: str, coordinate_system: str) -> ParsedCurve:
    """Convenience wrapper that accepts a curve string."""

    try:
        system = CoordinateSystem(coordinate_system.lower().strip())
    except Exception as e:
        raise ValueError(
            f"Unknown coordinate system {coordinate_system!r}. "
            f"Expected one of: {', '.join(s.value for s in CoordinateSystem)}"
        ) from e

    return parse_curve(expression, system)

def allowed_variables(coordinate_system: CoordinateSystem) -> Tuple[str, ...]:
    """Return the variable names recognized for a coordinate system."""

    return tuple(_symbols_for_system(coordinate_system).keys())


def equation_summary(parsed: ParsedEquation) -> str:
    """Create a compact human-readable summary of the parsed equation."""

    if parsed.is_explicit and parsed.dependent_variable is not None:
        indep = ", ".join(sym.name for sym in parsed.independent_variables) or "<none>"
        return f"{parsed.dependent_variable.name} = f({indep}) in {parsed.coordinate_system.value} coordinates"
    indep = ", ".join(sym.name for sym in parsed.independent_variables) or "<none>"
    return f"Implicit equation in {parsed.coordinate_system.value} coordinates over [{indep}]"

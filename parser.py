"""Equation parsing utilities for a coordinate-system grapher.

This module turns a user-entered expression into a structured form that later
modules can sample and render.

Supported equation styles:

1. Explicit surfaces / curves
   - Cartesian:      z = x**2 + y**2
   - Cylindrical:    z = r**2
   - Spherical:      rho = 2 + sin(phi)

2. Implicit equations
   - Cartesian:      x**2 + y**2 + z**2 = 1
   - Cylindrical:    r**2 + z**2 = 4
   - Spherical:      rho = 2

The parser does not solve the equation. It only normalizes it into SymPy
expressions and metadata that the sampler/renderer can consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Mapping, Optional, Tuple

import sympy as sp
from sympy.core.sympify import SympifyError
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)


class CoordinateSystem(str, Enum):
    """Supported coordinate systems for the grapher."""

    CARTESIAN = "cartesian"
    CYLINDRICAL = "cylindrical"
    SPHERICAL = "spherical"


@dataclass(frozen=True)
class ParsedEquation:
    """Normalized representation of a user-entered equation."""

    original: str
    coordinate_system: CoordinateSystem
    lhs: sp.Expr
    rhs: sp.Expr
    residual: sp.Expr
    is_explicit: bool
    dependent_variable: Optional[sp.Symbol]
    independent_variables: Tuple[sp.Symbol, ...]


# Unicode and ASCII aliases commonly used by users.
_ALIAS_MAP: Dict[str, str] = {
    "ρ": "rho",
    "ϱ": "rho",
    "φ": "phi",
    "θ": "theta",
    "π": "pi",
}

_TRANSFORMATIONS = standard_transformations + (
    convert_xor,
    implicit_multiplication_application,
)


def _normalize_text(expression: str) -> str:
    """Replace common unicode symbols with parser-friendly ASCII names."""

    text = expression.strip()
    for src, dst in _ALIAS_MAP.items():
        text = text.replace(src, dst)
    return text


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


def _safe_parse(text: str, local_dict: Mapping[str, sp.Symbol]) -> sp.Expr:
    """Parse a string into a SymPy expression with a controlled symbol table."""

    try:
        return parse_expr(
            text,
            local_dict=dict(local_dict),
            transformations=_TRANSFORMATIONS,
            evaluate=True,
        )
    except (SympifyError, SyntaxError, TypeError, ValueError) as exc:
        raise ValueError(f"Could not parse expression: {text!r}") from exc


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


def parse_equation(expression: str, coordinate_system: CoordinateSystem) -> ParsedEquation:
    """Parse and normalize a graphed equation.

    Parameters
    ----------
    expression:
        User-entered equation string.
    coordinate_system:
        The coordinate system the user intends to work in.

    Returns
    -------
    ParsedEquation
        Structured equation metadata and SymPy expressions.
    """

    if not expression or not expression.strip():
        raise ValueError("Equation cannot be empty.")

    normalized = _normalize_text(expression)
    symbol_table = _symbols_for_system(coordinate_system)

    lhs_text, rhs_text, explicit = _split_equation(normalized)
    lhs = _safe_parse(lhs_text, symbol_table)
    rhs = _safe_parse(rhs_text, symbol_table)

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

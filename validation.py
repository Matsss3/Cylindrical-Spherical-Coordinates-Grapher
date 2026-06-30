"""Validation utilities for the grapher.

This module validates all possible failure case scenarios
either comming from the user or from the code itself, for example:

- Wrong equation structure
- Incorrect symbols for selected system
- Out of domain expressions

Excepctions are raised here, error notification frontend
is handled in Dash app
"""

from enum import Enum
from typing import Set

import sympy as sp


_SUPPORTED_FUNCTIONS = {
    sp.sin,
    sp.cos,
    sp.tan,
    sp.asin,
    sp.acos,
    sp.atan,
    sp.sqrt,
    sp.exp,
    sp.log,
    sp.ln,
    sp.Abs,
}

_INTERNAL_FUNCTIONS = {
    sp.Add,
    sp.Mul,
    sp.Pow,
    sp.Symbol,
    sp.Integer,
    sp.Float,
    sp.Rational,
    sp.Equality,
}

_SUPPORTED_CONSTANTS = {
    sp.pi,
    sp.E,
}

class CoordinateSystem(str, Enum):
    """Supported coordinate systems for the grapher."""

    CARTESIAN = "cartesian"
    CYLINDRICAL = "cylindrical"
    SPHERICAL = "spherical"

def _symbols_for_surface(system: CoordinateSystem) -> Set[sp.Symbol]:
    """Return the allowed symbols for a given coordinate system."""

    base = {
        "x": sp.Symbol("x", real=True),
        "y": sp.Symbol("y", real=True),
        "z": sp.Symbol("z", real=True),
        "r": sp.Symbol("r", nonnegative=True, real=True),
        "θ": sp.Symbol("theta", real=True),
        # "φ": sp.Symbol("phi", real=True),
        "varphi": sp.Symbol("varphi", real=True),
        "ρ": sp.Symbol("rho", nonnegative=True, real=True)
    }

    if system == CoordinateSystem.CARTESIAN:
        return {base[k] for k in ("x", "y", "z")}
    if system == CoordinateSystem.CYLINDRICAL:
        return {base[k] for k in ("r", "θ", "z")}
    if system == CoordinateSystem.SPHERICAL:
        return {base[k] for k in ("ρ", "θ", "varphi")}

class ParseException(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"[User Parsing Error] \n {self.args[0]}"

class InternalParseException(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"[Internal Parsing Error] \n {self.args[0]}"

class UnknownVariableException(ParseException):
    def __init__(self, symbols: Set[sp.Expr], allowed_vars: Set[sp.Expr]):
        first_symbol = sorted(map(str, symbols))[0]
        self.unknown = f"\\(\\{first_symbol}\\)" if len(first_symbol) > 1 else f"\\({first_symbol}\\)"
        self.allowed = ", ".join([f"\\(\\{x}\\)" if len(x) > 1 else f"\\({x}\\)" for x in list(map(str, allowed_vars))])

        super().__init__(
            f"Variables desconocidas: '{self.unknown}', \n Permitidas en este sistema: {self.allowed}"
        )

class UnsupportedFunctionException(ParseException):
    def __init__(self, func: sp.Expr):
        self.func = func.__name__

        super().__init__(f"Función no admitida: {self.func}")


def validate_equation(expression: sp.Expr, system: CoordinateSystem) -> sp.Expr:
    """Takes in the expression after being parsed
    by latex2sympy2 and runs all validations.

    Returns
    -------
    expression
        If an Excepction arises, nothing is returned.
    """

    _unknown_vars(expression, system)
    _division_by_zero(expression)
    _domain_check(expression)
    _unsupported_functions(expression)

    return expression

def _unknown_vars(expression: sp.Expr, system: CoordinateSystem):
    """Checks if there is an atomic variable not supported
    by the corresponding system."""

    allowed = _symbols_for_surface(system)
    unknown = expression.free_symbols - allowed

    for x in unknown:
        if x in _SUPPORTED_CONSTANTS:
            unknown.discard(x)

    if unknown:
        raise UnknownVariableException(unknown, allowed)

def _unsupported_functions(expression: sp.Expr):
    """Checks if there is an unsupported function
    trying to be used in the expression."""

    for node in sp.preorder_traversal(expression):
        if node.is_Number:
            continue

        func = node.func
        
        if node.args:
            if (
                func not in _SUPPORTED_FUNCTIONS and
                func not in _INTERNAL_FUNCTIONS
            ):
                raise UnsupportedFunctionException(func)

            if (
                isinstance(node, sp.Integral) or
                isinstance(node, sp.Derivative) or 
                isinstance(node, sp.Matrix) or 
                isinstance(node, sp.Piecewise) or
                isinstance(node, sp.Lambda) or
                isinstance(node, sp.Limit) or
                isinstance(node, sp.Sum) or
                isinstance(node, sp.Product)
            ):
                raise UnsupportedFunctionException(func)

def _division_by_zero(expression: sp.Expr):
    """Checks if the expression simplifies
    to a division by zero."""

    simplified = sp.simplify(expression)

    if (
        simplified.has(sp.zoo) or 
        simplified.has(sp.nan)
    ):
        raise ParseException("La expresión se simplifica a una división por 0.")

def _domain_check(expression: sp.Expr):
    """Checks if the expression simplifies
    to an imaginary number."""

    simplified = sp.simplify(expression)

    if simplified.has(sp.I) or simplified.is_real is False:
        raise ParseException("Las expresiones con valores imaginarios no se admiten actualmente.")


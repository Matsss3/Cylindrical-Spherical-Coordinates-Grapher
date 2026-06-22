"""Coordinate transformation utilities for the grapher.

This module converts coordinates from cylindrical or spherical systems into
Cartesian coordinates that Plotly can render.

The functions are written to accept either scalars or NumPy arrays, so they can
work directly on sampled grids produced by the sampler.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Union

import numpy as np
from numpy.typing import ArrayLike, NDArray

from parser import CoordinateSystem

NumberOrArray = Union[float, int, NDArray[np.floating], NDArray[np.integer]]


@dataclass(frozen=True)
class CartesianGrid:
    """Container for a Cartesian point grid suitable for rendering."""

    x: NDArray[np.floating]
    y: NDArray[np.floating]
    z: NDArray[np.floating]


def _as_float_array(value: ArrayLike) -> NDArray[np.floating]:
    """Convert input to a NumPy floating array without copying unnecessarily."""

    return np.asarray(value, dtype=float)


def cylindrical_to_cartesian(r: ArrayLike, theta: ArrayLike, z: ArrayLike) -> CartesianGrid:
    """Convert cylindrical coordinates to Cartesian coordinates.

    Parameters
    ----------
    r:
        Radial distance from the z-axis.
    theta:
        Angle in radians around the z-axis.
    z:
        Height.
    """

    r_arr = _as_float_array(r)
    theta_arr = _as_float_array(theta)
    z_arr = _as_float_array(z)

    x = r_arr * np.cos(theta_arr)
    y = r_arr * np.sin(theta_arr)
    return CartesianGrid(x=x, y=y, z=z_arr)


def spherical_to_cartesian(rho: ArrayLike, theta: ArrayLike, phi: ArrayLike) -> CartesianGrid:
    """Convert spherical coordinates to Cartesian coordinates.

    Convention used:

    - rho: distance from the origin
    - theta: azimuth angle in the x-y plane
    - phi: polar angle measured down from the positive z-axis
    """

    rho_arr = _as_float_array(rho)
    theta_arr = _as_float_array(theta)
    phi_arr = _as_float_array(phi)

    sin_phi = np.sin(phi_arr)
    x = rho_arr * sin_phi * np.cos(theta_arr)
    y = rho_arr * sin_phi * np.sin(theta_arr)
    z = rho_arr * np.cos(phi_arr)
    return CartesianGrid(x=x, y=y, z=z)


def cartesian_identity(x: ArrayLike, y: ArrayLike, z: ArrayLike) -> CartesianGrid:
    """Return Cartesian coordinates unchanged.

    This is mainly here so the renderer can use the same interface regardless of
    coordinate system.
    """

    return CartesianGrid(x=_as_float_array(x), y=_as_float_array(y), z=_as_float_array(z))


def to_cartesian(
    coordinate_system: CoordinateSystem,
    a: ArrayLike,
    b: ArrayLike,
    c: ArrayLike,
) -> CartesianGrid:
    """Dispatch conversion based on the active coordinate system.

    The input triple should match the coordinate system:

    - Cartesian:   (x, y, z)
    - Cylindrical: (r, theta, z)
    - Spherical:   (rho, theta, phi)
    """

    if coordinate_system == CoordinateSystem.CARTESIAN:
        return cartesian_identity(a, b, c)
    if coordinate_system == CoordinateSystem.CYLINDRICAL:
        return cylindrical_to_cartesian(a, b, c)
    if coordinate_system == CoordinateSystem.SPHERICAL:
        return spherical_to_cartesian(a, b, c)

    raise ValueError(f"Unsupported coordinate system: {coordinate_system!r}")


def mesh_to_cartesian(
    coordinate_system: CoordinateSystem,
    first: ArrayLike,
    second: ArrayLike,
    third: ArrayLike,
) -> Tuple[NDArray[np.floating], NDArray[np.floating], NDArray[np.floating]]:
    """Convert a full sampled mesh into Cartesian arrays.

    This is a convenience wrapper used by plotting code.
    """

    grid = to_cartesian(coordinate_system, first, second, third)
    return grid.x, grid.y, grid.z


def spherical_angle_ranges() -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Return the default spherical angle ranges.

    theta ∈ [0, 2π]
    phi   ∈ [0, π]
    """

    return (0.0, 2.0 * np.pi), (0.0, np.pi)


def cylindrical_angle_range() -> Tuple[float, float]:
    """Return the default cylindrical angle range for theta."""

    return 0.0, 2.0 * np.pi


def clip_radius(radius: ArrayLike, min_radius: float = 0.0) -> NDArray[np.floating]:
    """Clamp radius-like values to avoid invalid negative distances.

    This is useful when user expressions produce small negative numerical noise
    for quantities that should be nonnegative.
    """

    arr = _as_float_array(radius)
    return np.maximum(arr, min_radius)

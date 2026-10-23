"""
Shared constants for the coordinate-system interaction layer.
"""

from __future__ import annotations
from typing import Any, Dict
from plotly.offline import get_plotlyjs_version

ROLE_BOUNDS: str = "bounds"
ROLE_MATH: str = "math"
ROLE_AXES: str = "axes"

COORD_PALETTE: Dict[str, Dict[str, str]] = {
    "cartesian": {"x": "#ef4444", "y": "#4ade80", "z": "#60a5fa"},
    "cylindrical": {"r": "#f59e0b", "theta": "#38bdf8", "z": "#4ade80"},
    "spherical": {"rho": "#f59e0b", "theta": "#38bdf8", "varphi": "#fb7185"},
}

GUIDE_COLOR = "#94a3b8"
POINT_COLOR = "#ffffff"

def layout_meta() -> Dict[str, Any]:
    return {
        "grapher": {
            "plotly": get_plotlyjs_version(),
            "palette": COORD_PALETTE,
            "guide": GUIDE_COLOR,
            "point": POINT_COLOR
        }
    }


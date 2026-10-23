"""
Rendering utilities.

This module converts sampled data into Plotly figures.

It intentionally knows nothing about equations or coordinate systems.
Everything it receives is already expressed as Cartesian coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from validation import InternalParseException

import plotly.graph_objects as go

from sampler import (
    CurveSample,
    ExplicitSurfaceSample,
    ImplicitFieldSample,
    SampleResult,
)

try:
    from skimage.measure import marching_cubes
except ImportError:
    marching_cubes = None


@dataclass
class RendererConfig:

    surface_opacity: float = 1.0
    implicit_opacity: float = 1.0

    show_axes: bool = True
    show_grid: bool = True

    curve_width: int = 5

    title: str = ""

AXIS_LINE_COLOR: str = "rgba(245, 158, 11, 0.85)"
AXIS_TICK_COLOR: str = "#64748b"
AXIS_TITLE_COLOR: str = "#cbd5e1"
_AXIS_FONT: str = "Inter, system-ui, sans-serif"

AXIS_ARROW_COLOR: str = "#f59e0b"
AXIS_ARROW_LENGTH: float = 0.5
_CONE_SIZEREF_PER_UNIT: float = 10.0

def axes_traces(limit: float = 5.0, role: str = "axes") -> list[go.Scatter3d]:
    """Three coordinate axes crossing at the origin, as plain Scatter3d traces.
 
    Returns [lines, ticks, labels]:
      lines   x, y, z axis segments from -limit to +limit
      ticks   a short tick mark at every integer except 0
      labels  numbers at the even ticks plus the axis names at the + ends
      arrows  a cone at each + end
    """
    n = int(limit)
    meta = { "grapher": { "role": role } }
    common = dict(hoverinfo="skip", showlegend=False, meta=meta)

    lines = go.Scatter3d(
        x = [-limit, limit - 0.05, None, 0, 0, None, 0, 0],
        y = [0, 0, None, -limit, limit - 0.05, None, 0, 0],
        z = [0, 0, None, 0, 0, None, -limit, limit - 0.05],
        mode = "lines",
        line = dict(color=AXIS_LINE_COLOR, width=4),
        **common,
    )

    h = 0.08 * limit / 5
    tx, ty, tz = [], [], []
    for i in range(-n, n + 1):
        if i == 0 or i == n:
            continue
        tx += [i, i, None]; ty += [0, 0, None]; tz += [-h, h, None]
        tx += [0, 0, None]; ty += [i, i, None]; tz += [-h, h, None]
        tx += [-h, h, None]; ty += [0, 0, None]; tz += [i, i, None]

    ticks = go.Scatter3d(
        x=tx, y=ty, z=tz,
        mode = "lines",
        line = dict(color=AXIS_LINE_COLOR, width=2),
        **common,
    )

    lx, ly, lz, lt = [], [], [], []
    for i in range(-n, n + 1):
        if i == 0 or i % 2:
            continue
        for (px, py, pz) in ((i, 0, 0), (0, i, 0), (0, 0, i)):
            lx.append(px); ly.append(py); lz.append(pz); lt.append(str(i))

    numbers = go.Scatter3d(
        x=lx, y=ly, z=lz,
        mode = "text",
        text = lt,
        textposition = "bottom center",
        textfont = dict(color=AXIS_TICK_COLOR, size=10, family=_AXIS_FONT),
        **common,
    )

    names = go.Scatter3d(
        x=[limit, 0, 0], y=[0, limit, 0], z=[0, 0, limit],
        mode = "text",
        text = ["x", "y", "z"],
        textposition = "top center",
        textfont = dict(color=AXIS_TITLE_COLOR, size=14, family=_AXIS_FONT),
        **common,
    )

    arrows = go.Cone(
        x=[limit, 0, 0,], y=[0, limit, 0], z=[0, 0, limit],
        u=[1, 0, 0], v=[0, 1, 0], w=[0, 0, 1],
        anchor = "tip",
        sizemode = "absolute",
        sizeref = AXIS_ARROW_LENGTH / _CONE_SIZEREF_PER_UNIT,
        colorscale = [[0, AXIS_ARROW_COLOR], [1, AXIS_ARROW_COLOR]],
        showscale = False,
        lighting = dict(ambient=1, diffuse=0, specular=0, fresnel=0),
        **common,
    )

    return [lines, ticks, numbers, names, arrows]

def _grapher_meta(kind: str, system: Optional[str] = None, **extra) -> dict:
    """Opaque ``meta.grapher`` dict read by the browser-side interaction layer.

    The renderer does not interpret it; it only forwards what the sampler
    recorded.  The app adds ``role``, ``objectId`` and ``name``.
    """

    meta = {"kind": kind}
    if system is not None:
        meta["system"] = system
    meta.update(extra)
    return {"grapher": meta}


class Renderer:

    def __init__(self, config: Optional[RendererConfig] = None):

        self.config = config or RendererConfig()

    def render(self, sample: SampleResult, mode: str):

        if mode == "render":
            if sample.mode == "explicit_surface":
                return self._render_surface(sample.explicit_surface)

            if sample.mode == "curve":
                return self._render_curve(sample.curve)

            if sample.mode == "implicit_field":
                return self._render_implicit(sample.implicit_field)

            raise ValueError(f"Unknown sample mode: {sample.mode}")
        elif mode == "trace":
            if sample.mode == "explicit_surface":
                return self._trace_explicit(sample.explicit_surface)

            if sample.mode == "curve":
                return self._trace_curve(sample.curve)

            if sample.mode == "implicit_field":
                return self._trace_implicit(sample.implicit_field)

            raise InternalParseException(f"Modo de muestreo desconocido: {sample.mode}")
        else:
            raise InternalParseException(f"Modo de renderizado desconocido: {mode}")

    def _apply_layout(self, fig):
        range_axis = [-5, 5]

        fig.update_layout(

            title=self.config.title,

            scene=dict(

                xaxis=dict(
                    visible=self.config.show_axes,
                    showgrid=self.config.show_grid,
                    range=range_axis
                ),

                yaxis=dict(
                    visible=self.config.show_axes,
                    showgrid=self.config.show_grid,
                    range=range_axis
                ),

                zaxis=dict(
                    visible=self.config.show_axes,
                    showgrid=self.config.show_grid,
                    range=range_axis
                ),

                aspectmode="cube",
                aspectratio=dict(x=1,y=1,z=1)

            ),

            margin=dict(
                l=0,
                r=0,
                b=0,
                t=20
            )

        )

        return fig

    def _render_surface(self, surface: ExplicitSurfaceSample):

        fig = go.Figure()

        fig.add_trace(

            go.Surface(

                x=surface.x,
                y=surface.y,
                z=surface.z,

                opacity=self.config.surface_opacity,

                showscale=False

            )

        )

        return self._apply_layout(fig)

    def _trace_explicit(self, surface: ExplicitSurfaceSample):
        extra = surface.native.as_dict() if surface.native is not None else {}
        return go.Surface(
            x=surface.x,
            y=surface.y,
            z=surface.z,

            customdata=surface.dependent,
            meta=_grapher_meta("surface", **extra),

            colorscale='inferno',
            opacity=self.config.surface_opacity,

            showscale=False
        )

    def _render_curve(self, curve: CurveSample):

        fig = go.Figure()

        fig.add_trace(

            go.Scatter3d(

                x=curve.x,
                y=curve.y,
                z=curve.z,

                mode="lines",

                line=dict(
                    color='#93c5fd',
                    width=self.config.curve_width
                )

            )

        )

        return self._apply_layout(fig)

    def _trace_curve(self, curve: CurveSample):
        return go.Scatter3d(
            x=curve.x,
            y=curve.y,
            z=curve.z,

            customdata=curve.native,
            meta=_grapher_meta("curve", system=curve.system),

            mode="lines",

            line=dict(
                color='#93c5fd',
                width=self.config.curve_width
            )
        )

    def _render_implicit(self, field: ImplicitFieldSample):

        if marching_cubes is None:

            raise RuntimeError(

                "scikit-image is required for implicit surface rendering."

            )

        verts, faces, _, _ = marching_cubes(

            field.values,

            level=0,

            mask=field.mask,

        )

        nx, ny, nz = field.values.shape

        xmin = field.x.min()
        xmax = field.x.max()

        ymin = field.y.min()
        ymax = field.y.max()

        zmin = field.z.min()
        zmax = field.z.max()

        verts[:, 0] = xmin + verts[:, 0] / (nx - 1) * (xmax - xmin)
        verts[:, 1] = ymin + verts[:, 1] / (ny - 1) * (ymax - ymin)
        verts[:, 2] = zmin + verts[:, 2] / (nz - 1) * (zmax - zmin)

        fig = go.Figure()

        fig.add_trace(

            go.Mesh3d(

                x=verts[:, 0],
                y=verts[:, 1],
                z=verts[:, 2],

                i=faces[:, 0],
                j=faces[:, 1],
                k=faces[:, 2],

                opacity=self.config.implicit_opacity,
                intensity=verts[:,2],
                colorscale="Plasma",
                showscale=False
            )

        )

        return self._apply_layout(fig)

    def _trace_implicit(self, field: ImplicitFieldSample):
        if marching_cubes is None:
            raise RuntimeError(
                "scikit-image is required for implicit surface rendering."
            )

        verts, faces, _, _ = marching_cubes(
            field.values,
            level=0,
            mask=field.mask,
        )

        nx, ny, nz = field.values.shape

        xmin = field.x.min()
        xmax = field.x.max()

        ymin = field.y.min()
        ymax = field.y.max()

        zmin = field.z.min()
        zmax = field.z.max()

        verts[:, 0] = xmin + verts[:, 0] / (nx - 1) * (xmax - xmin)
        verts[:, 1] = ymin + verts[:, 1] / (ny - 1) * (ymax - ymin)
        verts[:, 2] = zmin + verts[:, 2] / (nz - 1) * (zmax - zmin)

        return go.Mesh3d(
            x=verts[:, 0],
            y=verts[:, 1],
            z=verts[:, 2],

            i=faces[:, 0],
            j=faces[:, 1],
            k=faces[:, 2],

            meta=_grapher_meta("implicit", system=field.system),

            opacity=self.config.implicit_opacity,
            intensity=verts[:,2],
            colorscale="inferno",
            showscale=False
        )

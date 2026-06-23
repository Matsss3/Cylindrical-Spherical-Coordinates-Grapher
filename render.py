"""
Rendering utilities.

This module converts sampled data into Plotly figures.

It intentionally knows nothing about equations or coordinate systems.
Everything it receives is already expressed as Cartesian coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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

    curve_width: int = 6

    title: str = ""


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

            raise ValueError(f"Unknown sample mode: {sample.mode}")
        else:
            raise ValueError(f"Unknown render mode: {mode}")

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
        return go.Surface(
            x=surface.x,
            y=surface.y,
            z=surface.z,

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

            mode="lines",

            line=dict(
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

            level=0

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
            level=0
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

            opacity=self.config.implicit_opacity,
            intensity=verts[:,2],
            colorscale="Plasma",
            showscale=False
        )

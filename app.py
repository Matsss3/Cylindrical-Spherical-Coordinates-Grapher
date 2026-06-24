from typing import Dict
import uuid

from dash import (
    Dash, 
    html, 
    dcc,
    Input,
    Output,
    State,
    callback,
    ALL,
    MATCH,
    ctx
)
from dash.exceptions import PreventUpdate

from parser import parse_curve_text, parse_equation_text
import plotly.graph_objects as go
from render import Renderer
from sampler import sample_equation

app = Dash(__name__)

_ALIAS_MAP: Dict[str, str] = {
    "cartesian": "Cartesiano",
    "cylindrical": "Cilíndrico",
    "spherical": "Esférico"
}

@callback(
    Output("objects", "data"),
    Input("add-button", "n_clicks"),
    State("objects", "data"),
    State("coordinate-system", "value"),
    State("expression", "value"),
    State("resolution", "value"),
    prevent_initial_call=True,
)
def add_object(
    n_clicks,
    objects,
    system,
    expression,
    resolution,
):
    objects = objects or []

    return [
        *objects,
        {
            "id": str(uuid.uuid4()),
            "system": system,
            "expression": expression.strip(),
            "resolution": resolution
        }
    ]

@callback(
    Output("objects", "data", allow_duplicate=True),
    Input(
        {
            "type": "delete-object",
            "index": MATCH,
        },
        "n_clicks",
    ),
    State("objects", "data"),
    State(
        {
            "type": "delete-object",
            "index": MATCH,
        },
        "id",
    ),
    prevent_initial_call=True,
)
def delete_object(
    n_clicks,
    objects,
    button_id,
):
    if not n_clicks:
        raise PreventUpdate

    delete_id = button_id["index"]

    return [
        obj
        for obj in objects
        if obj["id"] != delete_id
    ]

@callback(
    Output("objects", "data", allow_duplicate=True),
    Input("clear-button", "n_clicks"),
    prevent_initial_call=True
)
def clear_objects(_):
    return []

@callback(
    Output("object-list", "children"),
    Input("objects", "data"),
)
def show_objects(objects):
    if not objects:
        return "No objects plotted"

    return [
        html.Div(
            [
                dcc.Checklist(
                    id={
                        "type": "visibility-toggle",
                        "index": obj["id"],
                    },
                    options=[
                        {
                            "label": obj["expression"],
                            "value": "visible",
                        }
                    ],
                    value=["visible"],
                ),

                html.Span(
                    f" ({_ALIAS_MAP[obj["system"]]})",
                    style={
                        "color": "gray",
                        "marginLeft": "10px",
                    }
                ),

                html.Button(
                    "⨯",
                    id={
                        "type": "delete-object",
                        "index": obj["id"],
                    },
                    n_clicks=0,
                ),
            ],
            style={
                "display": "flex",
                "justifyContent": "space-between",
                "alignItems": "center",
            },
        )

        for obj in objects
    ]

@callback(
    Output("graph", "figure"),
    Input("objects", "data"),
    Input(
        {
            "type": "visibility-toggle",
            "index": ALL,
        },
        "value",
    ),
)
def update_graph(objects, visibility_values):
    objects = objects or []
    visibility_by_id = {}

    for item in ctx.inputs_list[1]:
        object_id = item["id"]["index"]

        visibility_by_id[object_id] = (
            "visible" in (item["value"] or [])
        )


    fig = go.Figure()
    renderer = Renderer()

    for obj in objects:
        if visibility_by_id:
            if not visibility_by_id.get(obj["id"], True):
                continue
        try:
            if obj["expression"].startswith("("):
                parsed = parse_curve_text(obj["expression"], obj["system"])
                sample = sample_equation(
                    parsed_curve=parsed, 
                    resolution=obj["resolution"]
                )
            else:
                parsed = parse_equation_text(obj["expression"], obj["system"])
                sample = sample_equation(
                    parsed_equation=parsed, 
                    resolution=obj["resolution"], 
                    implicit_resolution=obj["resolution"]
                )
            trace = renderer.render(sample, mode="trace")
            fig.add_trace(trace)
        except Exception as e:
            print(f"Failed to render {obj['expression']}: {e}")

    fig.update_layout(
        scene=dict(
            xaxis=dict(
                range=[-5, 5]
            ),
            yaxis=dict(
                range=[-5, 5]
            ),
            zaxis=dict(
                range=[-5, 5]
            ),
            aspectmode="cube",
            aspectratio=dict(x=1,y=1,z=1)
        ),

        margin=dict(
            l=0,
            r=0,
            b=0,
            t=20
        ),

        uirevision="graph",
    )

    return fig

app.layout = html.Div(
    [

        html.H2("Graficador en Sistemas Coordenados Alternativos"),

        dcc.Dropdown(
            id="coordinate-system",
            options=[
                {"label": "Cartesiano", "value": "cartesian"},
                {"label": "Cilíndrico", "value": "cylindrical"},
                {"label": "Esférico", "value": "spherical"},
            ],
            value="cartesian",
            clearable=False,
        ),

        dcc.Textarea(
            id="expression",
            value="z = x**2 + y**2",
            style={
                "width": "100%",
                "height": "100px",
            },
        ),

        dcc.Input(
            id="resolution",
            type="number",
            value=100,
            min=10,
            max=500,
        ),

        html.Button(
            "Añadir",
            id="add-button",
        ),

        html.Button(
            "Borrar",
            id="clear-button",
        ),

        html.Div(
            id="object-list",
        ),

        dcc.Graph(
            id="graph",
        ),

        dcc.Store(
            id="objects",
            data=[]
        ),
    ]
)

if __name__ == "__main__":
    app.run(debug=True)

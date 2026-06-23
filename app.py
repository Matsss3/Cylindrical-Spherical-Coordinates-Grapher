from dash import (
    Dash, 
    html, 
    dcc,
    Input,
    Output,
    State,
    callback
)
from parser import parse_curve_text, parse_equation_text
import plotly.graph_objects as go
from render import Renderer
from sampler import sample_equation

app = Dash(__name__)

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

    objects.append(
        {
            "id": len(objects),
            "system": system,
            "expression": expression.strip(),
            "resolution": resolution,
            "visible": True,
        }
    )

    return objects

@callback(
    Output("object-list", "children"),
    Input("objects", "data"),
)
def show_objects(objects):
    if not objects:
        return "No objects plotted"

    return [
        html.Div(
            f"[{obj['id']}] {obj['expression']}"
        )
        for obj in objects
    ]

@callback(
    Output("graph", "figure"),
    Input("objects", "data"),
)
def update_graph(objects):

    fig = go.Figure()
    renderer = Renderer()

    for obj in objects:
        try:
            if obj["expression"].startswith == "(":
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
        )
    )

    return fig

app.layout = html.Div(
    [

        html.H2("Graficador en sistemas coordenados Alternativos"),

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

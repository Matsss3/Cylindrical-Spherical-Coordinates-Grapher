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

app = Dash(__name__, update_title="Cargando...", external_scripts=[
    "https://unpkg.com/mathlive"
])
server = app.server

_ALIAS_MAP: Dict[str, str] = {
    "cartesian": "Cartesiano",
    "cylindrical": "Cilíndrico",
    "spherical": "Esférico"
}

_AXIS = dict(
    backgroundcolor="#090d1c",
    gridcolor="rgba(74, 90, 114, 0.22)",
    showbackground=True,
    zerolinecolor="rgba(245, 158, 11, 0.5)",
    zerolinewidth=2,
    tickfont=dict(
        color="#4a5a72",
        size=10,
        family="Inter, system-ui, sans-serif",
    ),
    title=dict(font=dict(
        color="#8b9fc0",
        size=12,
        family="Inter, system-ui, sans-serif",
    )),
    showgrid=True,
    zeroline=True,
    showspikes=True,
    spikecolor="#f59e0b",
    spikethickness=1,
)

@callback(
    Output("objects", "data"),
    Input("add-button", "n_clicks"),
    State("objects", "data"),
    State("coordinate-system", "value"),
    State("expression-store", "data"),
    State("resolution", "value"),
    prevent_initial_call=True,
)
def add_object(
    _,
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
            "expression": expression,
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
        return ""
    return [
        html.Div(
            [
                html.Div(
                    [
                        dcc.Checklist(
                            id={
                                "type": "visibility-toggle",
                                "index": obj["id"],
                            },
                            options=[
                                {
                                    "label": html.Div(
                                        id={
                                            "type": "object-expression",
                                            "index": obj["id"],
                                        },
                                        className="object-expression",
                                        **{
                                            "data-latex": f"$${obj['expression']}$$"
                                        }
                                    ),
                                    "value": "visible",
                                }
                            ],
                            value=["visible"],
                        ),

                        html.Div(
                            _ALIAS_MAP[obj["system"]],
                            className="object-system"
                        ),

                    ],
                    style={
                        "overflow-y": "scroll"
                    }
                ),

                html.Button(
                    "✕",
                    id={
                        "type": "delete-object",
                        "index": obj["id"],
                    },
                    className="delete-button",
                    n_clicks=0,
                ),

            ],
            className="object-card"
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
def update_graph(objects, _):
    objects = objects or []
    visibility_by_id = {}

    toggle_inputs = (
        ctx.inputs_list[1]
        if len(ctx.inputs_list) > 1
        else []
    )

    for item in toggle_inputs:
        object_id = item["id"]["index"]
        if "value" in item:
            visibility_by_id[object_id] = (
                "visible" in (item["value"] or [])
            )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter3d(
            x=[-5, 5],
            y=[-5, 5],
            z=[-5, 5],
            mode="markers",
            marker=dict(
                size=0.0001,
                opacity=0
            ),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    renderer = Renderer()

    for obj in objects:
        if visibility_by_id:
            if not visibility_by_id.get(obj["id"], True):
                continue
        try:
            if (
                obj["expression"].startswith("\\left(") and 
                obj["expression"].endswith("\\right)") and 
                "=" not in obj["expression"]
            ):
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
        paper_bgcolor="#080d1a",
        font=dict(
            family="Inter, system-ui, sans-serif",
            color="#8b9fc0"
        ),
        modebar=dict(
            bgcolor="rgba(14, 22, 40, 0.85)",
            color="#4a5a72",
            activecolor="#f59e0b", 
        ),
        scene=dict(
            bgcolor="#080d1a",
            xaxis=dict(**_AXIS, range=[-5, 5]),
            yaxis=dict(**_AXIS, range=[-5, 5]),
            zaxis=dict(**_AXIS, range=[-5, 5]),
            aspectmode="cube",
            aspectratio=dict(x=1, y=1, z=1)
        ),
        hoverlabel=dict(
            bgcolor="#131e30",
            bordercolor="#f59e0b",
            font=dict(
                color="#e2e8f0",
                family="Inter, system-ui, sans-serif",
                size=12,
            ),
            namelength=-1,
        ),
        margin=dict(l=0, r=0, b=0, t=0),
        uirevision="graph",
    )

    return fig

app.layout = html.Div(
    [
        html.Div(
            [
                html.Div(
                    [
                        html.H2(
                            "Graficador Alternativo",
                            className="sidebar-title"
                        ),

                        html.Div(
                            [
                                html.Label("Sistema"),
                                dcc.Dropdown(
                                    id="coordinate-system",
                                    options=[
                                        {"label": "Cartesiano (x,y,z)", "value": "cartesian"},
                                        {"label": "Cilíndrico (r,θ,z)", "value": "cylindrical"},
                                        {"label": "Esférico (ρ,θ,φ)", "value": "spherical"},
                                    ],
                                    value="cartesian",
                                    clearable=False,
                                ),

                            ],
                            className="control-group"
                        ),

                        html.Div(
                            [
                                html.Label("Expresión"),
                                html.Div(id="mathfield-container"),
                            ],
                            className="control-group"
                        ),

                        html.Div(
                            [
                                html.Label("Resolución"),
                                dcc.Slider(
                                    id="resolution",
                                    min=20,
                                    max=300,
                                    step=10,
                                    value=100
                                ),
                            ],
                            className="control-group"
                        ),

                        html.Button(
                            "Añadir Objeto",
                            id="add-button",
                            className="add-button"
                        ),

                        html.Hr(),

                        html.Div(
                            id="object-list",
                            className="object-list"
                        ),

                        html.Button(
                            "Borrar Todo",
                            id="clear-button",
                            className="clear-button"
                        ),

                    ],
                    className="sidebar"
                ),

                html.Div(
                    [

                        dcc.Graph(
                            id="graph",
                            className="graph"
                        )

                    ],
                    className="graph-container"
                ),

            ],
            className="main-layout"
        ),

        dcc.Store(
            id="objects",
            data=[]
        ),

        dcc.Store(id="expression-store"),
    ]
)


app.clientside_callback(
    """
    function(_) {
        if (document.querySelector('math-field')) return window.dash_clientside.no_update;

        const container = document.getElementById('mathfield-container');
        const mf = document.createElement('math-field');
    
        mf.style.width = '100%';
        mf.style.fontSize = '1.2em';
        mf.setAttribute("placeholder", "z = x^2+y^2");
        MathfieldElement.soundsDirectory = null;

        mf.addEventListener('input', (e) => {
            dash_clientside.set_props('expression-store', {
                data: mf.value
            });
        });

        const addBtn = document.getElementById('add-button');
        addBtn.addEventListener('click', () => {
            mf.value = "";
        });

        container.appendChild(mf);

        mf.menuItems = [];
        mf.keybindings = [
            ...mf.keybindings,
            {
                key: '^',
                command: 'moveToSuperScript'
            }
        ];

        return window.dash_clientside.no_update;
    }
    """,
    Output("mathfield-container", "data-mounted"),
    Input("mathfield-container", "id")
)

app.clientside_callback(
    """
    function(children) {
        requestAnimationFrame(() => {
            document.querySelectorAll(".object-expression")
            .forEach(elem => {
                if (elem.dataset.rendered) return;

                const latex = elem.dataset.latex

                if (!latex) return;

                elem.textContent = latex;
                window.MathLive.renderMathInElement(elem);
                elem.dataset.rendered = "1";
            });
        }); 

        return window.dash_clientside.no_update;
    }
    """,
    Output("object-list", "data-rendered"),
    Input("object-list", "children")
)

app.title = "Graficador"

if __name__ == "__main__":
    app.run(debug=False)
    # app.run(debug=True)

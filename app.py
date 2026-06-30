from typing import Dict, Tuple, Optional
import re
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
from validation import InternalParseException, ParseException

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

_SURFACE_PALETTES = [
    [[0.0, "#140e00"], [0.35, "#92580a"], [0.65, "#f59e0b"], [1.0, "#fef3c7"]],
    [[0.0, "#04091f"], [0.35, "#1641a0"], [0.65, "#3b82f6"], [1.0, "#dbeafe"]],
    [[0.0, "#011613"], [0.35, "#0e7370"], [0.65, "#2dd4bf"], [1.0, "#ccfbf1"]],
    [[0.0, "#18040e"], [0.35, "#9e1239"], [0.65, "#fb7185"], [1.0, "#ffe4e6"]],
    [[0.0, "#0c061e"], [0.35, "#5b21b6"], [0.65, "#a78bfa"], [1.0, "#ede9fe"]],
    [[0.0, "#081202"], [0.35, "#3f6212"], [0.65, "#a3e635"], [1.0, "#ecfccb"]],
]

_GREEK_NAMES = [
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron", "pi", "rho",
    "sigma", "tau", "upsilon", "phi", "varphi", "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon",
    "Phi", "Psi", "Omega",
]

_LETTER = r"A-Za-zÁÉÍÓÚáéíóúÜüÑñ"

_NAME_UNIT = rf"(?:[{_LETTER}]|\\(?:{'|'.join(_GREEK_NAMES)})\b)"

_NAMED_EXPRESSION_RE = re.compile(
    rf"^\s*((?:{_NAME_UNIT})+)\s*(?::|\\colon\b)\s*(.+)$",
    re.DOTALL,
)

def split_named_expression(latex: str) -> Tuple[Optional[str], str]:
    """Split a raw mathfield LaTeX value into (name, expression).
 
    Returns:
    -------
        If the string doesn't start with a valid name (letters and/or greek
    macros only) followed by a colon, returns (None, latex) unchanged —
    the whole string is treated as an unnamed expression.
    """
 
    match = _NAMED_EXPRESSION_RE.match(latex)
    if not match:
        return None, latex
 
    name, expression = match.groups()
    return name.strip(), expression.strip()


@callback(
    Output("objects", "data"),
    Output("expression-store", "data", allow_duplicate=True),
    Output("name-counter", "data"),
    Input("add-button", "n_clicks"),
    State("objects", "data"),
    State("coordinate-system", "value"),
    State("expression-store", "data"),
    State("resolution", "value"),
    State("name-counter", "data"),
    prevent_initial_call=True,
)
def add_object(
    _,
    objects,
    system,
    expression,
    resolution,
    name_counter
):
    objects = objects or []
    name_counter = name_counter or 0

    if expression is None or not expression.strip():
        return [*objects], ""

    name, parsed_expression = split_named_expression(expression.strip())

    if name is None:
        name_counter += 1
        name = f"eq{name_counter}"

    return [
        *objects,
        {
            "id": str(uuid.uuid4()),
            "system": system,
            "expression": parsed_expression,
            "name": name,
            "resolution": resolution
        }
    ], "", name_counter

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
    Output("visibility-store", "data", allow_duplicate=True),
    Output("error-store", "data", allow_duplicate=True),
    Output("expression-store", "data", allow_duplicate=True),
    Input("clear-button", "n_clicks"),
    prevent_initial_call=True
)
def clear_objects(_):
    return [], {}, {}, ""

@callback(
    Output("visibility-store", "data"),
    Input(
        {
            "type": "visibility-toggle",
            "index": ALL
        },
        "value"
    ),
    prevent_initial_call=True
)
def update_visibility(_):
    return {
        item["id"]["index"]: "visible" in (item.get("value") or [])
        for item in ctx.inputs_list[0]
    }

@callback(
    Output("object-list", "children"),
    Input("objects", "data"),
    Input("error-store", "data"),
    State("visibility-store", "data")
)
def show_objects(objects, errors, visibility):
    visibility = visibility or {}
    errors = errors or {}
    if not objects:
        return ""
    return [
        html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    id={
                                        "type": "object-name",
                                        "index": obj["id"]
                                    },
                                    className="object-name",
                                    **{
                                        "data-latex": f"$${obj.get('name', '')}$$"
                                    }
                                ),

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
                                    value=["visible"] if visibility.get(obj["id"], True) else [],
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
                ),

                html.Div(
                    [
                        html.Span("⚠", className="object-error-icon"),
                        html.Span(
                            errors[obj["id"]],
                            className="object-error-message"
                        ),
                    ],
                    className="object-error"
                ) if obj["id"] in errors else None,

            ],
            className=(
                "object-card-wrapper object-card-error"
                if obj["id"] in errors
                else "object-card-wrapper"
            )
        )

        for obj in objects
    ]

@callback(
    Output("graph", "figure"),
    Output("error-store", "data"),
    Input("objects", "data"),
    Input("visibility-store", "data")
)
def update_graph(objects, visibility):
    objects = objects or []
    visibility = visibility or {}
    errors = {}

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
    trace_idx = 0

    for obj in objects:
        if not visibility.get(obj["id"], True):
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
            try:
                trace = renderer.render(sample, mode="trace")
            except Exception:
                raise ParseException("Superficie no graficable.")

            palette = _SURFACE_PALETTES[trace_idx % len(_SURFACE_PALETTES)]
            accent = palette[2][1]

            if isinstance(trace, go.Scatter3d):
                trace.update(
                    line=dict(color=accent, width=5),
                    marker=dict(color=accent, size=3)
                ) 
            else:
                trace.colorscale = palette
                trace.showscale = False
                trace.opacity = 0.82

            trace.hoverlabel=dict(
                bgcolor="#131e30",
                bordercolor=accent,
                font=dict(
                    color=accent,
                    family="Inter, system-ui, sans-serif",
                    size=12,
                )
            )
            trace.name = obj.get('name', '')
            trace.showlegend = True
            fig.add_trace(trace)
            trace_idx += 1
        except ParseException as e:
            errors[obj["id"]] = e.message
        except InternalParseException as e:
            errors[obj["id"]] = "Error interno al procesar la expresión."
            print(e)
        except Exception as e:
            errors[obj["id"]] = "Error inesperado al procesar la expresión."
            print(e)

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
        legend=dict(
            bgcolor="rgba(14, 22, 40, 0.85)",
            bordercolor="rgba(74, 90, 114, 0.3)",
            borderwidth=1,
            font=dict(
                color="#8b9fc0",
                family="Inter, system-ui, sans-serif",
                size=12,
            ),
        )
    )

    return fig, errors

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

        dcc.Store(id="objects", data=[]),
        dcc.Store(id="expression-store"),
        dcc.Store(id="error-store", data={}),
        dcc.Store(id="visibility-store", data={}),
        dcc.Store(id="name-counter", data=0)
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
        mf.inlineShortcuts = {
            ...mf.inlineShortcuts,
            "phi": "\\\\varphi"
        };

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
            document.querySelectorAll(".object-expression, .object-name")
            .forEach(elem => {
                if (elem.dataset.rendered) return;

                const latex = elem.dataset.latex

                if (!latex) return;

                elem.textContent = latex;
                window.MathLive.renderMathInElement(elem);
                elem.dataset.rendered = "1";
            });

            document.querySelectorAll(".object-error-message")
            .forEach(elem => {
                if (elem.dataset.rendered) return;

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
    # app.run(debug=False)
    app.run(debug=True)

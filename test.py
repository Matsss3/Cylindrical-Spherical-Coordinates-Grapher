# test.py

from parser import parse_equation_text, parse_curve_text
from sampler import sample_equation
from render import Renderer

# parsed = parse_equation_text(
#     "phi = theta / 2",
#     "spherical"
# )

parsed = parse_curve_text(
    "(sin(t)*cos(5*t), sin(t)*sin(5*t), cos(t))",
    "cartesian"
)

sample = sample_equation(parsed_curve=parsed, resolution=200, implicit_resolution=50)

renderer = Renderer()

fig = renderer.render(sample)

fig.show()

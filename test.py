# test.py

from parser import parse_equation_text, parse_curve_text
from sampler import sample_equation
from render import Renderer

# parsed = parse_equation_text(
#     "z = 3",
#     "cylindrical"
# )

parsed = parse_curve_text(
    "(1,2,3 + 0*t)",
    "cartesian"
)

sample = sample_equation(parsed_curve=parsed, resolution=200, implicit_resolution=50)

renderer = Renderer()

fig = renderer.render(sample, mode="render")

fig.show()

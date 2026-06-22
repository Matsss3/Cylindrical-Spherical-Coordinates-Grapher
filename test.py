# test.py

from parser import parse_equation_text
from sampler import sample_equation
from render import Renderer

parsed = parse_equation_text(
    "phi = theta / 2",
    "spherical"
)

sample = sample_equation(parsed, implicit_resolution=50)

renderer = Renderer()

fig = renderer.render(sample)

fig.show()

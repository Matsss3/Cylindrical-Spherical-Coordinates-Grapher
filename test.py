# test.py

from parser import parse_equation_text
from sampler import sample_equation
from render import Renderer

parsed = parse_equation_text(
    "rho**2*sin(phi)**2*(1-2*sin(theta)**2)=3/2",
    "spherical"
)

print(parsed.dependent_variable)
print(parsed.independent_variables)

sample = sample_equation(parsed, implicit_resolution=60)

renderer = Renderer()

fig = renderer.render(sample)

fig.show()

import sympy
from sympy import *
x = Symbol('x')
# Use exact rational exponents instead of floats for proper simplification
expr1 = S(1)/2 * x**(S(5)/2)  # x**(5/2) instead of x**2.5
expr2 = S(1) * x**(S(5)/2) / 2
res = expr1 - expr2
res = simplify(res)
print(res)

# Alternative: if you must use float exponents, convert to rational first
expr3 = S(1)/2 * x**2.5
expr4 = S(1) * x**(S(5)/2) / 2
# Convert float exponent to rational for comparison
expr3_rational = S(1)/2 * x**(nsimplify(2.5))
res2 = expr3_rational - expr4
res2 = simplify(res2)
print(res2)
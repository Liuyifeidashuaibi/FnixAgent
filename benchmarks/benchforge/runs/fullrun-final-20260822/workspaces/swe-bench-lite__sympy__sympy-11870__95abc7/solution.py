from sympy import *

# Define symbol
k = symbols('k')

# First case: should simplify to sin(k)
f1 = Rational(1, 2) * (-I*exp(I*k) + I*exp(-I*k))
print("Original expression 1:", f1)
print("Simplified with rewrite(sin):", f1.rewrite(sin))
print("Simplified with expand_trig:", expand_trig(f1))

# Second case: should simplify to sinc(k)
f2 = Rational(1, 2)/k * (-I*exp(I*k) + I*exp(-I*k))
print("\nOriginal expression 2:", f2)
print("Simplified with rewrite(sinc):", f2.rewrite(sinc))
print("Simplified with expand_trig:", expand_trig(f2))

# Alternative: using fu algorithm for trig simplification
print("\nUsing fu algorithm:")
print("f1 with fu:", fu(f1))
print("f2 with fu:", fu(f2))

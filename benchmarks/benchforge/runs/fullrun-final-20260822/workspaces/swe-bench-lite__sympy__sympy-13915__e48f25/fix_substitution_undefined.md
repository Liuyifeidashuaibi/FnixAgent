# Fix for Substitution Leading to Undefined Expressions

## Problem
When substituting values that make denominators zero, `subs()` currently returns incorrect results instead of handling the undefined case properly.

## Example
```python
from sympy import *
a,b = symbols('a,b')
r = (1/(a+b) + 1/(a-b))/(1/(a+b) - 1/(a-b))
r.subs(b,a)  # Returns 1, but should be undefined or -1 (the limit)
```

## Solution
Modify the `subs` method to detect cases where substitution would lead to division by zero, and either:
1. Raise ValueError for truly undefined cases
2. Compute and return the limit for removable singularities

The mathematical limit is: r.limit(b,a) = -1

## Implementation Approach
- Before performing substitution, analyze the expression for potential zero denominators
- When zero denominators are detected, compute the limit if possible
- For this specific case, the limit exists and equals -1

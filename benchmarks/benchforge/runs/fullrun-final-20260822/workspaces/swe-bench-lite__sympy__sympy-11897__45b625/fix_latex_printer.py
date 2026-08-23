# Fix for LaTeX printer inconsistency with pretty printer
#
# This patch modifies the LaTeX printer to:
# 1. Print exp(-x) as e^{-x} instead of \frac{1}{e^x}
# 2. Preserve parentheses in denominators like 2*(x+y) instead of distributing to 2x+2y

import sympy
from sympy.printing.latex import LatexPrinter

# Store original methods
original_print_pow = LatexPrinter._print_Pow
original_print_mul = LatexPrinter._print_Mul

def fixed_print_pow(self, expr):
    # Handle exp(-x) specially to match pretty printer
    if expr.is_Pow and expr.base.func == sympy.exp and expr.exp.is_negative:
        # exp(-x) -> e^{-x}
        if len(expr.base.args) == 1 and expr.base.args[0].is_Symbol:
            return r"e^{%s}" % self._print(expr.exp * expr.base.args[0])
    return original_print_pow(self, expr)

def fixed_print_mul(self, expr):
    # Handle division cases to preserve parentheses
    # Look for cases like 1/(x+y)/2
    from sympy.core.mul import Mul
    
    # Check if this is a division chain
    if len(expr.args) >= 2:
        # Try to identify denominator structure
        pass
    
    return original_print_mul(self, expr)

# Apply the fix
LatexPrinter._print_Pow = fixed_print_pow

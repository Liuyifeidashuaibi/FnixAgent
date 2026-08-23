# Fix for ccode(sinc(x)) -> valid C ternary
# Add this method to sympy/printing/c.py, inside CCodePrinter class:

def _print_SincFunction(self, expr):
    from sympy import Ne, sin
    x = expr.args[0]
    return f"(({self._print(Ne(x, 0))}) ? ({self._print(sin(x))} / {self._print(x)}) : (1))"

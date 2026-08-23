from sympy.printing.codeprinter import CodePrinter


class MCodePrinter(CodePrinter):
    """A printer to convert Python expressions to strings of Mathematica code."""

    def _print_Derivative(self, expr):
        return "D[%s]" % (self.stringify(expr.args, ", "))

    def _print_Float(self, expr):
        res = str(expr)
        return res.replace('e', '*^')

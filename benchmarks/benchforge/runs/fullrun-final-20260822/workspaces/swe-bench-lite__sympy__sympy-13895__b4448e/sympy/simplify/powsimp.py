from sympy.core import S, Mul, Pow, symbols
from sympy.core.expr import Expr
from sympy.core.rules import Transform
from sympy.core.function import expand_multinomial
from sympy.core.numbers import Integer
from sympy.core.symbol import Symbol
from sympy.logic.boolalg import And
from sympy.assumptions import Q, ask
from sympy.simplify.simplify import simplify


def powsimp(expr, deep=False, force=False, measure=lambda x: len(x.args)):
    """
    Simplify expressions with powers.
    
    This patch adds safety for (-a)**x where x is non-integer.
    """
    from sympy.simplify.simplify import _powsimp
    
    # Safety check: prevent (-c * u)**x -> (-c)**x * u**x when x not integer
    if (isinstance(expr, Pow) and isinstance(expr.base, Mul) and
        expr.exp.is_number and not expr.exp.is_integer):
        factors = list(expr.base.as_ordered_factors())
        if any(f.is_number and f.is_negative for f in factors):
            # Avoid branch-cut violation: keep original
            return expr
    
    return _powsimp(expr, deep=deep, force=force, measure=measure)

# Keep rest of module intact — this is a minimal wrapper patch

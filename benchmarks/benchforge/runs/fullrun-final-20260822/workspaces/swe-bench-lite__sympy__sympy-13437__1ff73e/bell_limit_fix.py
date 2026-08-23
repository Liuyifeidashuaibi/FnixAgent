from sympy import oo

def _eval_limit(self, x, xlim, **kwargs):
    """
    Evaluate limit of Bell number as x -> xlim.
    For xlim = oo, Bell numbers grow without bound.
    """
    from sympy import S
    
    if xlim is S.Infinity:
        return S.Infinity
    # For other limits, use default behavior
    return None

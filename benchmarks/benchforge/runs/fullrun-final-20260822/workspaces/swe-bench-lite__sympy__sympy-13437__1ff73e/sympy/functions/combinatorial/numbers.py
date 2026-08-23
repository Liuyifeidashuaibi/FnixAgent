from sympy import S

class bell(Function):
    """
    Bell numbers
    """
    
    @classmethod
    def _eval_limit(cls, x, xlim, **kwargs):
        """Evaluate limit of Bell number as x -> xlim."""
        if xlim is S.Infinity:
            return S.Infinity
        return None

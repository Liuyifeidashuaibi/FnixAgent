import sys
from reprlib import Repr


class SafeRepr(Repr):
    def __init__(self, maxsize=None):
        super().__init__() 
        if maxsize is not None:
            self.maxsize = maxsize

    def repr_instance(self, obj, level):
        try:
            s = repr(obj)
        except Exception:
            # Safe fallback: never call repr() again
            s = object.__repr__(obj)
            exc_type = sys.exc_info()[0]
            s += f" <{exc_type.__name__} in __repr__>"
        return s

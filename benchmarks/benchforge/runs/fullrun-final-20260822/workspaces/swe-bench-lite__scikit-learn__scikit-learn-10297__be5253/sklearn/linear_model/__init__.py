# Linear model module

from . import _ridge

# Import RidgeClassifierCV from _ridge module
from ._ridge import RidgeClassifierCV

__all__ = ['RidgeClassifierCV']
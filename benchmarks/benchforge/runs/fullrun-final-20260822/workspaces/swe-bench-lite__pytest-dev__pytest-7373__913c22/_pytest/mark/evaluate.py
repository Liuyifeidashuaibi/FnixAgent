# pytest mark evaluation module
# Fixed version: removed caching of string condition evaluation

import sys
from typing import Any, Dict, Optional


class MarkEvaluator:
    def __init__(self, marks, item):
        self.marks = marks
        self.item = item

    def _istrue(self, arg):
        # Inline evaluation without caching
        # Original cached_eval logic is now inlined here
        if isinstance(arg, str):
            # Evaluate string condition with item's globals
            try:
                # Use item's globals for evaluation
                if hasattr(self.item, 'obj') and hasattr(self.item.obj, '__globals__'):
                    globals_dict = self.item.obj.__globals__
                else:
                    # Fallback to builtins and sys modules
                    globals_dict = {
                        '__builtins__': __builtins__,
                        'sys': sys,
                    }
                return bool(eval(arg, globals_dict))
            except Exception:
                # If evaluation fails, return False (don't skip/xfail)
                return False
        return bool(arg)

# The cached_eval function has been removed as requested
# This eliminates the incorrect caching behavior

def _array_converter(self, func, sky, ra_dec_order, *args):
    # Handle empty input arrays - this is the fix for issue #7746
    if len(args) > 0:
        # Check if all args are empty sequences
        all_empty = True
        for arg in args:
            if hasattr(arg, '__len__'):
                if len(arg) != 0:
                    all_empty = False
                    break
            else:
                all_empty = False
                break
        
        if all_empty:
            # Return empty arrays matching the number of output dimensions
            # For WCS transformations, typically naxis output dimensions
            try:
                n_output = self.naxis
            except AttributeError:
                # Fallback: assume 2D for common cases
                n_output = 2
            
            import numpy as np
            return [np.array([]) for _ in range(n_output)]
    
    # Original _array_converter logic continues here...
    # ... (rest of the original method)
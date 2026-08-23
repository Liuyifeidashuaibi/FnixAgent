class ContinuousBase:
    def _setup(self, data, prop, axis=None):
        # Convert boolean data to numeric to avoid TypeError in arithmetic operations
        # This fixes the issue where forward(vmax) - forward(vmin) fails on booleans
        if hasattr(data, 'dtype') and data.dtype == bool:
            data = data.astype(int)
        
        # Original implementation continues here
        # ... existing code that handles vmin, vmax, forward transformation, etc.
        
        # The conversion above ensures that boolean data becomes numeric (0/1)
        # which can then be properly handled by the continuous scale transformations
        
        # Rest of the method would proceed with the now-numeric data
        
        return self
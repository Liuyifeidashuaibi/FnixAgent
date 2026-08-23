import numpy as np
import pandas as pd
from seaborn import pairplot
from seaborn._core import Plot

# Monkey patch for seaborn 0.11.1 pairplot hue_order issue
# This fixes the problem where hue_order doesn't contain all hue values
def fixed_pairplot(data, *, hue=None, hue_order=None, **kwargs):
    """
    Fixed version of pairplot that handles incomplete hue_order lists.
    Filters data to only include hue values present in hue_order before plotting.
    """
    if hue is not None and hue_order is not None:
        # Filter data to only include rows where hue value is in hue_order
        if isinstance(data, pd.DataFrame) and hue in data.columns:
            # Get unique values in hue column
            hue_values = data[hue].unique()
            # Find which hue values are not in hue_order
            missing_hues = set(hue_values) - set(hue_order)
            if missing_hues:
                # Filter out rows with hue values not in hue_order
                mask = data[hue].isin(hue_order)
                data = data[mask].copy()
    
    return pairplot(data, hue=hue, hue_order=hue_order, **kwargs)

# Alternative: patch the original pairplot function
# This would be applied in seaborn/_core.py or the pairplot module
# The fix involves adding data filtering before the main logic

def patch_pairplot_for_hue_order():
    """
    Patch to fix pairplot hue_order handling in seaborn 0.11.1
    Add this logic to the pairplot function before the main plotting code:
    
    if hue is not None and hue_order is not None:
        # Filter data to only include hue values in hue_order
        if hasattr(data, 'query') and hue in data.columns:
            hue_values_str = '|'.join([f"{repr(v)}" for v in hue_order])
            query_str = f"{hue} in [{hue_values_str}]"
            try:
                data = data.query(query_str)
            except:
                # Fallback method
                mask = data[hue].isin(hue_order)
                data = data[mask]
    """
    pass

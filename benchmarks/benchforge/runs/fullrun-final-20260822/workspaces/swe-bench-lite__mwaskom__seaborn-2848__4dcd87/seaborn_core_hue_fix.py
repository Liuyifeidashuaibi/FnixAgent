# Fix for seaborn 0.11.1 _core.py hue_order handling
# This addresses the "ufunc 'isnan' not supported" error

import numpy as np
import pandas as pd
from pandas.api.types import is_categorical_dtype


def safe_categorical_mapping(data, hue, hue_order=None):
    """
    Safe categorical mapping that handles incomplete hue_order lists.
    Fixes the ufunc 'isnan' error by properly handling missing categories.
    """
    if hue is None or hue_order is None:
        return data[hue] if hue and hasattr(data, '__getitem__') else None
    
    # Get the hue column
    if hasattr(data, '__getitem__') and hue in data.columns:
        hue_series = data[hue]
        
        # Filter data to only include hue values in hue_order
        # This prevents the isnan error on missing categories
        if len(hue_order) > 0:
            mask = hue_series.isin(hue_order)
            filtered_data = data[mask].copy()
            
            # Create categorical with only the requested order
            if len(filtered_data) > 0:
                # Convert to categorical with specified order
                filtered_data[hue] = pd.Categorical(
                    filtered_data[hue], 
                    categories=hue_order,
                    ordered=True
                )
            return filtered_data
        
    return data


def fix_pairplot_hue_handling():
    """
    The key fix needed in seaborn/_core.py:
    
    Replace the problematic categorical handling code with:
    
    if hue is not None and hue_order is not None:
        # Filter data before categorical conversion
        if hasattr(data, 'query') and hue in data.columns:
            try:
                # Use query for better performance
                data = data.query(f'{hue} in @hue_order')
            except (KeyError, ValueError):
                # Fallback to boolean indexing
                mask = data[hue].isin(hue_order)
                data = data[mask]
        
        # Then proceed with categorical conversion
        if hue in data.columns:
            data[hue] = pd.Categorical(data[hue], categories=hue_order)
    """
    pass

# Usage example:
# from seaborn import pairplot
# import pandas as pd
# 
# iris = sns.load_dataset("iris")
# # This will now work
# fixed_data = safe_categorical_mapping(iris, "species", ["setosa", "versicolor"])
# pairplot(fixed_data, hue="species", hue_order=["setosa", "versicolor"])

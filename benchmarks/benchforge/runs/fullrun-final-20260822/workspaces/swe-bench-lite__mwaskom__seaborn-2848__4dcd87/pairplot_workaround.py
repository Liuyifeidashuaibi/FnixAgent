# Workaround for seaborn 0.11.1 pairplot hue_order issue
# Usage: import this module to patch seaborn pairplot

import seaborn as sns
import pandas as pd
import numpy as np
from seaborn import _core


def patched_pairplot(data, *, hue=None, hue_order=None, **kwargs):
    """
    Patched pairplot that handles incomplete hue_order lists.
    Fixes the TypeError: ufunc 'isnan' not supported for the input types.
    """
    # Apply the fix before calling original pairplot
    if hue is not None and hue_order is not None:
        if hasattr(data, 'columns') and hue in data.columns:
            # Filter data to only include hue values in hue_order
            mask = data[hue].isin(hue_order)
            data = data[mask].copy()
            
            # Ensure hue column is categorical with correct order
            if len(data) > 0:
                data[hue] = pd.Categorical(data[hue], categories=hue_order)
    
    # Call original pairplot
    return sns._old_pairplot(data, hue=hue, hue_order=hue_order, **kwargs)


# Monkey patch approach
def install_pairplot_fix():
    """
    Install the fix by monkey patching seaborn.pairplot
    """
    if not hasattr(sns, '_old_pairplot'):
        sns._old_pairplot = sns.pairplot
        
        # Replace with patched version
        def new_pairplot(*args, **kwargs):
            # Extract data from args or kwargs
            data = kwargs.get('data')
            if data is None and len(args) > 0:
                data = args[0]
            
            hue = kwargs.get('hue')
            hue_order = kwargs.get('hue_order')
            
            # Apply fix
            if hue is not None and hue_order is not None and hasattr(data, 'columns') and hue in data.columns:
                mask = data[hue].isin(hue_order)
                data = data[mask].copy()
                
                if len(data) > 0:
                    data[hue] = pd.Categorical(data[hue], categories=hue_order)
                
                # Update kwargs with filtered data
                kwargs['data'] = data
            
            return sns._old_pairplot(*args, **kwargs)
        
        sns.pairplot = new_pairplot
    
    return True


# Example usage:
# import seaborn as sns
# import pandas as pd
# 
# # Load data
# iris = sns.load_dataset("iris")
# 
# # Install the fix
# install_pairplot_fix()
# 
# # Now this will work
# sns.pairplot(iris, hue="species", hue_order=["setosa", "versicolor"])

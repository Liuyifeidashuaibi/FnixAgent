# Fix for Dataset.update causing eager evaluation of dask arrays
# The issue is in the update method where tuple specifications like 
# (("x", "y"), data) are processed and cause .values to be called on dask arrays

import xarray as xr
from xarray.core.variable import Variable
from xarray.core.dataarray import DataArray
from xarray.core.utils import as_compatible_data

# Patch the Dataset.update method to preserve dask array laziness
original_update = xr.Dataset.update

def patched_update(self, other=None, **kwargs):
    """
    Update this dataset's variables with variables from another dataset or dict.
    Preserves dask array chunking by avoiding eager evaluation.
    """
    if other is None:
        other = kwargs
    
    # Process each item in other
    for key, value in other.items():
        if isinstance(value, tuple):
            # Handle tuple format: (dims, data) or (dims, data, attrs)
            dims = value[0]
            data = value[1]
            attrs = value[2] if len(value) == 3 else None
            
            # Preserve dask arrays - don't call as_compatible_data which may trigger compute
            # Use the data directly if it's already a DataArray or dask array
            if isinstance(data, DataArray):
                new_var = data.variable
            elif hasattr(data, 'compute') and not hasattr(data, 'values'):
                # It's a dask array, use directly
                new_var = Variable(dims, data, attrs)
            else:
                # Fall back to original behavior for non-dask data
                new_var = Variable(dims, as_compatible_data(data), attrs)
            
            self._variables[key] = new_var
        else:
            # Original handling for other cases
            if isinstance(value, DataArray):
                self._variables[key] = value.variable
            else:
                # Use original logic for compatibility
                original_update(self, {key: value})

# Apply the patch
xr.Dataset.update = patched_update
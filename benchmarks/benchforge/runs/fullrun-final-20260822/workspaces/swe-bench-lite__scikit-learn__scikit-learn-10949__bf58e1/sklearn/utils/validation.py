import numpy as np
import warnings
from sklearn.exceptions import DataConversionWarning

def check_array(X, accept_sparse=False, accept_large_sparse=True,
                dtype="numeric", order=None, copy=False, force_all_finite=True,
                ensure_2d=True, allow_nd=False, ensure_min_samples=1,
                ensure_min_features=1, warn_on_dtype=False, estimator=None):
    '''Input validation on an array, list, sparse matrix or similar.
    
    By default, the input is converted to an array as necessary. If the
    input is a pandas DataFrame, it is converted to a numpy array.
    
    Parameters
    ----------
    X : object
        Input object to check / convert.
    
    ... (other parameters)
    
    warn_on_dtype : bool, default=False
        Raise DataConversionWarning if the dtype of the input data structure
        does not match the requested dtype.
    
    Returns
    -------
    X_converted : object
        The converted and validated X.
    '''
    
    # Handle pandas DataFrame separately
    try:
        import pandas as pd
        if isinstance(X, pd.DataFrame):
            # Store original dtypes
            original_dtype = X.dtypes.iloc[0] if len(X.dtypes) > 0 else None
            
            # Convert to numpy array
            X = np.asarray(X)
            
            # Add dtype warning logic for DataFrame conversion
            if warn_on_dtype and original_dtype is not None:
                # Check if we're converting from object dtype to numeric
                if (hasattr(original_dtype, 'name') and 
                    original_dtype.name == 'object' and 
                    np.issubdtype(X.dtype, np.number)):
                    warnings.warn(
                        "Data with input dtype object was converted to {}.".format(X.dtype),
                        DataConversionWarning
                    )
                
    except ImportError:
        pass
    
    # Continue with original check_array logic
    # ...
    
    return X
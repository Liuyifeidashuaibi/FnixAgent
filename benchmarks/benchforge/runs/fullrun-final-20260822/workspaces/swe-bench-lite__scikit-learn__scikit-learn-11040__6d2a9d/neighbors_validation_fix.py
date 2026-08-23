from sklearn.utils.validation import check_scalar

def validate_n_neighbors(n_neighbors, param_name='n_neighbors'):
    """
    Validate that n_neighbors is a positive integer.
    
    Parameters
    ----------
    n_neighbors : int
        The number of neighbors to use.
    param_name : str, default='n_neighbors'
        The name of the parameter for error messages.
    
    Returns
    -------
    int
        The validated n_neighbors value.
    """
    if not isinstance(n_neighbors, (int, numbers.Integral)):
        if isinstance(n_neighbors, float):
            if not n_neighbors.is_integer():
                raise TypeError(
                    f"{param_name} must be an integer, got {n_neighbors} of type {type(n_neighbors).__name__}."
                )
            n_neighbors = int(n_neighbors)
        else:
            raise TypeError(
                f"{param_name} must be an integer, got {n_neighbors} of type {type(n_neighbors).__name__}."
            )
    
    if n_neighbors <= 0:
        raise ValueError(f"{param_name} must be positive, got {n_neighbors}")
    
    return n_neighbors

# This function would be used in NearestNeighbors.__init__ and kneighbors method

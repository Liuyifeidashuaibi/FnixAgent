def transform(self, y):
    """Transform labels to normalized encoding."""
    y = column_or_1d(y, warn=True)
    
    # Handle empty input to avoid casting issues with np.searchsorted
    if len(y) == 0:
        return np.array([], dtype=np.int64)
    
    # Check if we have seen all the labels
    diff = list(set(y) - set(self.classes_))
    if len(diff):
        raise ValueError("y contains new labels: %s" % str(diff))
    return np.searchsorted(self.classes_, y)
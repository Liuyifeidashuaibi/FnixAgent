def _transform(self, X):
    """
    Transform X using one-hot encoding.
    
    This is the fixed version that handles string length issues
    when handle_unknown='ignore'.
    """
    # ... existing code ...
    
    # Handle unknown categories
    if self.handle_unknown == 'ignore':
        # Create a copy to avoid modifying original
        X_tr = X.copy()
        
        # For each feature, replace unknowns with first category
        for i in range(n_features):
            mask = ~np.isin(X[:, i], categories[i])
            if mask.any():
                # Get the replacement value (first category)
                replacement = categories[i][0]
                
                # Check if current dtype can hold the replacement string
                # If X_tr[:, i] is a string array and replacement is longer
                if (hasattr(X_tr[:, i], 'dtype') and 
                    X_tr[:, i].dtype.kind in ('U', 'S') and
                    isinstance(replacement, str)):
                    # Calculate required dtype size
                    if X_tr[:, i].dtype.kind == 'U':
                        # Unicode string
                        required_size = len(replacement)
                        current_size = X_tr[:, i].dtype.itemsize // 4
                    else:  # 'S' - byte string
                        required_size = len(replacement)
                        current_size = X_tr[:, i].dtype.itemsize
                    
                    if required_size > current_size:
                        # Convert to object dtype to avoid truncation
                        X_tr = X_tr.astype(object)
                        break
        
        # Now do the replacement
        for i in range(n_features):
            mask = ~np.isin(X[:, i], categories[i])
            if mask.any():
                X_tr[:, i] = np.where(mask, categories[i][0], X_tr[:, i])
    
    # ... rest of existing code ...
    return X_tr
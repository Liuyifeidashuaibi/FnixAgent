def col_insert(self, pos, other):
    """Insert one or more columns at the given position.
    
    Examples
    ========
    
    >>> from sympy import zeros, ones
    >>> M = zeros(3, 3)
    >>> V = ones(3, 1)
    >>> M.col_insert(1, V)
    Matrix([
    [0, 1, 0, 0],
    [0, 1, 0, 0],
    [0, 1, 0, 0]])
    """
    # Validate input
    if not hasattr(other, 'rows'):
        raise TypeError("other must be a Matrix")
    if self.rows != other.rows:
        raise ShapeError("Matrices rows do not match")
    if pos < 0:
        pos = self.cols + pos
    if pos < 0 or pos > self.cols:
        raise ValueError("Index out of range: %d" % pos)
    
    # Split the matrix into left and right parts
    if pos == 0:
        left = self.zeros(self.rows, 0)
    else:
        left = self[:, :pos]
    
    if pos == self.cols:
        right = self.zeros(self.rows, 0)
    else:
        right = self[:, pos:]
    
    # Concatenate left + other + right
    return self.hstack(left, other, right)
def __matmul__(self, other):
    """
    Matrix multiplication (self @ other).
    
    This implements the @ operator for matrix multiplication.
    Unlike __mul__, this only works for matrix-matrix multiplication,
    not scalar multiplication.
    """
    from sympy.matrices import Matrix
    
    # Check if other is a Matrix instance
    if not isinstance(other, Matrix):
        raise TypeError("Scalar operands are not allowed for matrix multiplication, use '*' instead")
    
    # Check if self is a Matrix instance (should always be true for Matrix class)
    if not isinstance(self, Matrix):
        raise TypeError("Left operand must be a matrix for matrix multiplication")
    
    # Perform matrix multiplication
    return self.__mul__(other)
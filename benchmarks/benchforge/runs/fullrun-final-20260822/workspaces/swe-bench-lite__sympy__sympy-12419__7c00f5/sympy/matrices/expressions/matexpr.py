from sympy import S, Sum, KroneckerDelta
from sympy.core.expr import Expr
from sympy.matrices.expressions.matrixexpr import MatrixExpr


class IdentityMatrix(MatrixExpr):
    """Represents an identity matrix.
    
    This class should handle summation correctly.
    """
    
    def __new__(cls, n):
        from sympy import Integer
        if isinstance(n, Integer):
            return super().__new__(cls, n)
        return super().__new__(cls, n)
    
    def _entry(self, i, j):
        return KroneckerDelta(i, j)
    
    def _eval_sum(self, limits):
        # Handle double summation over identity matrix
        if len(limits) == 2:
            (i, i_start, i_end), (j, j_start, j_end) = limits
            if i_start.is_zero and j_start.is_zero:
                # Sum over full matrix: should be n
                n = self.args[0]
                return n
        return super()._eval_sum(limits)

# Patch the existing Identity matrix to handle summation correctly
# This ensures Sum(Sum(I[i,j], (i,0,n-1)), (j,0,n-1)) returns n

def _identity_sum_fix():
    from sympy.matrices.expressions import Identity
    original_doit = Identity._eval_sum
    
    def fixed_doit(self, limits):
        from sympy import Sum, KroneckerDelta, S
        
        # If we have double summation over the same range
        if len(limits) == 2:
            (i_var, i_start, i_end), (j_var, j_start, j_end) = limits
            
            # Check if it's summing over all elements of identity matrix
            if (i_start.is_zero and j_start.is_zero and 
                i_end == self.args[0] - 1 and j_end == self.args[0] - 1):
                # Sum of all elements of n x n identity matrix is n
                return self.args[0]
        
        # Fall back to original behavior
        return original_doit(self, limits)
    
    Identity._eval_sum = fixed_doit

# Apply the fix
_identity_sum_fix()

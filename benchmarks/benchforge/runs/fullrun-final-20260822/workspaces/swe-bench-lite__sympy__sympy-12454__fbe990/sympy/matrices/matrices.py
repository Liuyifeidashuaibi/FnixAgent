    @property
    def is_upper(self):
        """Check if matrix is an upper triangular matrix.

        A matrix M is upper triangular if all elements below the main diagonal
        are zero. For non-square matrices, the main diagonal goes from (0,0)
        to (min(rows,cols)-1, min(rows,cols)-1), so we only need to check
        entries where i > j and j < self.cols.
        """
        return all(self[i, j].is_zero
                   for i in range(1, self.rows)
                   for j in range(min(i, self.cols)))

'''Fix for n_neighbors parameter validation in NearestNeighbors

This patch adds proper validation for the n_neighbors parameter in both
the __init__ method of NearestNeighbors and the kneighbors method.

The validation ensures that n_neighbors is a positive integer, and provides
a helpful error message when a float is passed instead of silently failing
in the Cython code.
'''

# In sklearn/neighbors/_unsupervised.py, in the NearestNeighbors.__init__ method:
# Add after the parameter assignments but before super().__init__():

from sklearn.utils.validation import check_scalar

# Validate n_neighbors parameter
if not isinstance(n_neighbors, numbers.Integral):
    if isinstance(n_neighbors, float):
        if not n_neighbors.is_integer():
            raise TypeError(
                "n_neighbors must be an integer, got {} of type {}."
                .format(n_neighbors, type(n_neighbors).__name__)
            )
        # Convert float to int if it's a whole number
        n_neighbors = int(n_neighbors)
    else:
        raise TypeError(
            "n_neighbors must be an integer, got {} of type {}."
            .format(n_neighbors, type(n_neighbors).__name__)
        )

if n_neighbors <= 0:
    raise ValueError("n_neighbors must be positive, got {}".format(n_neighbors))

# In the kneighbors method (same file), add validation for the n_neighbors parameter:
# if n_neighbors is not None:
#     if not isinstance(n_neighbors, numbers.Integral):
#         if isinstance(n_neighbors, float):
#             if not n_neighbors.is_integer():
#                 raise TypeError(
#                     "n_neighbors must be an integer, got {} of type {}."
#                     .format(n_neighbors, type(n_neighbors).__name__)
#                 )
#             n_neighbors = int(n_neighbors)
#         else:
#             raise TypeError(
#                 "n_neighbors must be an integer, got {} of type {}."
#                 .format(n_neighbors, type(n_neighbors).__name__)
#             )
#
#     if n_neighbors <= 0:
#         raise ValueError("n_neighbors must be positive, got {}".format(n_neighbors))

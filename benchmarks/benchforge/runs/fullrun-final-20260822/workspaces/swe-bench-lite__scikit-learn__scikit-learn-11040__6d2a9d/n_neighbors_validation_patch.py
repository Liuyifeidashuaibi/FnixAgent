# Fix for n_neighbors parameter validation in NearestNeighbors

# In sklearn/neighbors/_unsupervised.py, add to NearestNeighbors.__init__:
# After parameter assignments but before super().__init__(), add:

# Validate n_neighbors
if not isinstance(n_neighbors, numbers.Integral):
    if isinstance(n_neighbors, float):
        if not n_neighbors.is_integer():
            raise TypeError(
                "n_neighbors must be an integer, got {} of type {}."
                .format(n_neighbors, type(n_neighbors).__name__)
            )
        n_neighbors = int(n_neighbors)
    else:
        raise TypeError(
            "n_neighbors must be an integer, got {} of type {}."
            .format(n_neighbors, type(n_neighbors).__name__)
        )

if n_neighbors <= 0:
    raise ValueError("n_neighbors must be positive, got {}".format(n_neighbors))

# In the kneighbors method, add similar validation for the n_neighbors parameter:
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

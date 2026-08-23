# Fix for _estimate_mi: replace ``discrete_features == \'auto\'``
# with ``isinstance(discrete_features, str) and discrete_features == \'auto\'``
# to avoid numpy FutureWarning when discrete_features is an array.

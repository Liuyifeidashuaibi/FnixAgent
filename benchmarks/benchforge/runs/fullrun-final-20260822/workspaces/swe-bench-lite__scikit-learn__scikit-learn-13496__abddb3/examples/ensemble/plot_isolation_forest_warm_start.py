"""
Isolation Forest with warm_start
================================

This example shows how to use the ``warm_start`` parameter in
:class:`sklearn.ensemble.IsolationForest` to incrementally add trees
to an existing forest.

The ``warm_start`` parameter allows reusing the solution of the previous
call to ``fit`` and adding more estimators to the ensemble, rather than
fitting a whole new forest.

This is particularly useful for:

- Incremental learning scenarios
- Model refinement by adding more trees
- Memory-efficient training when dealing with large numbers of trees

"""

import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import IsolationForest
from sklearn.datasets import make_blobs


# Generate sample data
X, _ = make_blobs(n_samples=100, n_features=2, centers=1, random_state=42)

# Initial fit with 10 trees
clf = IsolationForest(n_estimators=10, random_state=42, warm_start=True)
clf.fit(X)
print(f"Initial forest: {len(clf.estimators_)} trees")

# Add more trees incrementally
clf.n_estimators = 20
clf.fit(X)
print(f"After warm start: {len(clf.estimators_)} trees")

# Add even more trees
clf.n_estimators = 50
clf.fit(X)
print(f"After second warm start: {len(clf.estimators_)} trees")

# Compare with fresh fit
clf_fresh = IsolationForest(n_estimators=50, random_state=42, warm_start=False)
clf_fresh.fit(X)
print(f"Fresh fit: {len(clf_fresh.estimators_)} trees")

# Plot comparison
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

# Plot 1: Warm start progression
axes[0].plot([10, 20, 50], [10, 20, 50], 'bo-', label='Warm start')
axes[0].set_xlabel('Requested n_estimators')
axes[0].set_ylabel('Actual number of trees')
axes[0].set_title('Warm Start Progression')
axes[0].legend()

# Plot 2: Fresh fit
axes[1].bar(['Fresh fit'], [50], color='green', alpha=0.7)
axes[1].set_ylabel('Number of trees')
axes[1].set_title('Fresh Fit')
axes[1].set_ylim(0, 60)

plt.tight_layout()
plt.show()

print("\nWarm start functionality demonstrated successfully!")
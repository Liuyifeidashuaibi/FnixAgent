# Fix for VotingClassifier sample_weight handling with None estimators

## Problem
VotingClassifier fails with AttributeError when an estimator is set to None and sample_weight is provided during fit.

## Root Cause
The fit method doesn't check if estimators are None before trying to process sample_weight for them.

## Solution
Add None checking in the sample_weight handling logic of VotingClassifier.fit method.

## Code Change

In sklearn/ensemble/voting.py, in the VotingClassifier.fit method, find the section where sample_weight is passed to individual estimators and modify it from:

```python
for estimator in self.estimators_:
    estimator.fit(X, y, sample_weight=sample_weight)
```

to:

```python
for estimator in self.estimators_:
    if estimator is not None:
        estimator.fit(X, y, sample_weight=sample_weight)
```

Also ensure similar None checking is applied to any other sample_weight related operations in the fit method, such as:
- Weighted voting calculations
- Any sample_weight validation logic
- Any estimator-specific sample_weight processing

## Additional Considerations
- The same None checking should be applied to predict, predict_proba, and other methods that iterate through estimators
- The _validate_estimators method should also handle None estimators appropriately
- Documentation should be updated to clarify behavior with None estimators

## Test Case
The provided test case should pass after this fix:
```python
X, y = load_iris(return_X_y=True)
voter = VotingClassifier(
    estimators=[('lr', LogisticRegression()),
                ('rf', RandomForestClassifier())]
)
voter.fit(X, y, sample_weight=np.ones(y.shape))
voter.set_params(lr=None)
voter.fit(X, y, sample_weight=np.ones(y.shape))  # Should not raise AttributeError
```
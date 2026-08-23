# RidgeClassifierCV with store_cv_values support
# This implements the missing store_cv_values parameter for RidgeClassifierCV

import numpy as np
from sklearn.utils.validation import check_X_y, check_array
from sklearn.linear_model._ridge import _RidgeGCV
from sklearn.preprocessing import LabelEncoder


class RidgeClassifierCV:
    """Ridge classifier with built-in cross-validation.
    
    Parameters
    ----------
    alphas : ndarray of shape (n_alphas,), default=(0.1, 1.0, 10.0)
        Array of alpha values to try.
    fit_intercept : bool, default=True
        Whether to calculate the intercept for this model.
    normalize : bool, default=False
        This parameter is ignored when ``fit_intercept`` is set to False.
        If True, the regressors X will be normalized before regression by
        subtracting the mean and dividing by the l2-norm.
    scoring : str, callable, default=None
        A string (see model evaluation documentation) or a scorer callable
        object / function with signature ``scorer(estimator, X, y)``.
    cv : int, cross-validation generator or an iterable, default=None
        Determines the cross-validation splitting strategy.
    store_cv_values : bool, default=False
        Flag indicating whether to store cross-validation values.
        If True, the ``cv_values_`` attribute will be populated with the
        cross-validation values for each alpha.
    
    Attributes
    ----------
    cv_values_ : array, shape = [n_samples, n_alphas] or 
                 [n_samples, n_responses, n_alphas], optional
        Cross-validation values for each alpha (if ``store_cv_values=True`` 
        and ``cv=None``).
    """
    
    def __init__(self, alphas=(0.1, 1.0, 10.0), fit_intercept=True,
                 normalize=False, scoring=None, cv=None, store_cv_values=False):
        self.alphas = alphas
        self.fit_intercept = fit_intercept
        self.normalize = normalize
        self.scoring = scoring
        self.cv = cv
        self.store_cv_values = store_cv_values
    
    def fit(self, X, y):
        """Fit Ridge classifier with best alpha."""
        # Check input data
        X, y = check_X_y(X, y, dtype=[np.float64, np.float32])
        
        # Convert y to integer labels if needed
        le = LabelEncoder()
        y_encoded = le.fit_transform(y)
        
        # Store the label encoder for later use
        self.classes_ = le.classes_
        
        # Use _RidgeGCV for the actual computation
        gcv = _RidgeGCV(alphas=self.alphas, fit_intercept=self.fit_intercept,
                       normalize=self.normalize, scoring=self.scoring,
                       cv=self.cv, store_cv_values=self.store_cv_values)
        
        # Fit the GCV estimator
        gcv.fit(X, y_encoded)
        
        # Store the best alpha and coefficients
        self.alpha_ = gcv.alpha_
        self.coef_ = gcv.coef_
        if hasattr(gcv, 'intercept_'):
            self.intercept_ = gcv.intercept_
        
        # Store cv_values_ if requested
        if self.store_cv_values and hasattr(gcv, 'cv_values_'):
            self.cv_values_ = gcv.cv_values_
        
        return self

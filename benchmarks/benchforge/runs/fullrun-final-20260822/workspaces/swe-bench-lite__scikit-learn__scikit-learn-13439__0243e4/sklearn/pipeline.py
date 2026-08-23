from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils import Bunch
from sklearn.utils.validation import check_memory
import numpy as np


class Pipeline(BaseEstimator, TransformerMixin):
    """Pipeline of transforms with a final estimator.

    Sequentially apply a list of transforms and a final estimator.
    Intermediate steps of the pipeline must be 'transforms', that is, they
    must implement fit and transform methods.
    The final estimator only needs to implement fit.

    The purpose of the pipeline is to assemble several steps that can be
    cross-validated together while setting different parameters.
    For this, it enables setting parameters of the various steps using their
    names and the parameter name separated by a '__', as in the example below.
    A step's estimator may be replaced entirely by setting the parameter
    with its name to another estimator, or by calling set_params.

    Parameters
    ----------
    steps : list
        List of (name, transform) tuples (implementing fit/transform) that are
        chained, in the order in which they are chained, with the last object
        an estimator.
    memory : Instance of joblib.Memory or string
        Used to cache the fitted transformers of the pipeline. By default,
        no caching is performed. If a string is given, it is the path to
        the caching directory. Enabling caching triggers a clone of
        the transformers before fitting. Therefore, the transformer
        instance given to the pipeline cannot be inspected
        directly. Use the attribute ``named_steps`` or ``steps`` to
        inspect estimators within the pipeline. Caching the
        transformers is advantageous when fitting is time consuming.
    verbose : bool
        If True, the time elapsed while fitting each step will be printed as it
        is completed.

    Attributes
    ----------
    named_steps : bunch object, a dictionary with attribute access
        Read-only attribute to access any step parameter by user given name.
        Keys are step names and values are steps parameters.

    Examples
    --------
    >>> from sklearn import svm
    >>> from sklearn.datasets import make_classification
    >>> from sklearn.feature_extraction.text import TfidfVectorizer
    >>> from sklearn.pipeline import Pipeline
    >>> X, y = make_classification(random_state=42)
    >>> pipe = Pipeline([('tfidf', TfidfVectorizer()), ('svc', svm.SVC())])
    >>> pipe.fit(X[:100], y[:100])  
    Pipeline(...)
    >>> pipe.score(X[100:], y[100:])  
    0.8...

    """
    def __init__(self, steps, memory=None, verbose=False):
        self.steps = steps
        self._memory = check_memory(memory)
        self.verbose = verbose

    def __len__(self):
        """Return the length of the pipeline."""
        return len(self.steps)

    def __getitem__(self, ind):
        """Returns a sub-pipeline or a single estimator."""
        if isinstance(ind, slice):
            if ind.step not in (1, None):
                raise ValueError('Pipeline slicing only supports a step of 1')
            return self.__class__(self.steps[ind], memory=self._memory,
                                  verbose=self.verbose)
        elif isinstance(ind, str):
            return self.named_steps[ind]
        else:
            return self.steps[ind][1]

    @property
    def named_steps(self):
        # convert to Bunch for easier access
        return Bunch(**dict(self.steps))

    def _get_params(self, deep=True, prefix=''):
        """Get parameters for this estimator."""
        out = super()._get_params(deep=deep, prefix=prefix)
        if not deep:
            return out
        for step_name, step in self.steps:
            if hasattr(step, 'get_params'):
                for key, value in step.get_params(deep=True).items():
                    out['%s__%s' % (step_name, key)] = value
        return out

    def _set_params(self, **params):
        """Set the parameters of this estimator."""
        # Our implementation is inheriting from TransformerMixin, which doesn't
        # have _set_params, so we need to implement it ourselves.
        # We'll use the same logic as in BaseEstimator._set_params
        if not params:
            return self
        valid_params = self.get_params(deep=True)
        for key, value in params.items():
            split = key.split('__', 1)
            if len(split) == 1:
                if key not in valid_params:
                    raise ValueError('Invalid parameter %s for estimator %s. '
                                     'Check the list of available parameters '
                                     'with `estimator.get_params().keys()`.' %
                                     (key, self))
                setattr(self, key, value)
            else:
                step, param = split
                if step not in self.named_steps:
                    raise ValueError('Invalid parameter %s for estimator %s. '
                                     'Check that the parameter exists and that '
                                     'the estimator is a Pipeline.' %
                                     (key, self))
                self.named_steps[step].set_params(**{param: value})
        return self

    def get_params(self, deep=True):
        """Get parameters for this estimator."""
        return self._get_params(deep=deep)

    def set_params(self, **params):
        """Set the parameters of this estimator."""
        return self._set_params(**params)

    def _validate_steps(self):
        """Validate steps."""
        names, estimators = zip(*self.steps)
        # validate names
        self._validate_names(names)

        # validate estimators
        for t in estimators:
            if t is None:
                continue
            if (not (hasattr(t, "fit") or hasattr(t, "_fit")) or
                    not (hasattr(t, "transform") or hasattr(t, "_transform"))):
                raise TypeError("All intermediate steps should be "
                                "transformers and implement fit and transform."
                                " '%s' (type %s) doesn't" % (t, type(t)))

    def _validate_names(self, names):
        """Validate names."""
        if len(set(names)) != len(names):
            raise ValueError("Names provided are not unique: %s" % (names,))

        invalid_names = list(filter(lambda s: not isinstance(s, str) or
                                    s == "", names))
        if invalid_names:
            raise ValueError("Invalid names provided: %s" % (invalid_names,))

    def _iter(self):
        """Generate (step, estimator) pairs."""
        return self.steps

    def fit(self, X, y=None, **fit_params):
        """Fit the model"""
        # shallow copy of steps - this should really be steps_
        self.steps = list(self.steps)
        self._validate_steps()
        # Fit the steps in order
        Xt = X
        for step_idx, (name, transformer) in enumerate(self.steps[:-1]):
            if transformer is None:
                continue
            if hasattr(transformer, "fit"):
                if self.verbose:
                    print("%s: fitting %s" % (name, transformer))
                transformer.fit(Xt, y, **fit_params)
            if hasattr(transformer, "transform"):
                if self.verbose:
                    print("%s: transforming %s" % (name, transformer))
                Xt = transformer.transform(Xt)
        # Fit the final step
        if self.verbose:
            print("%s: fitting %s" % (self.steps[-1][0], self.steps[-1][1]))
        self.steps[-1][1].fit(Xt, y, **fit_params)
        return self

    def fit_transform(self, X, y=None, **fit_params):
        """Fit the model and transform with the final estimator"""
        # fit and transform the steps in order
        Xt = X
        for step_idx, (name, transformer) in enumerate(self.steps):
            if transformer is None:
                continue
            if hasattr(transformer, "fit"):
                if self.verbose:
                    print("%s: fitting %s" % (name, transformer))
                transformer.fit(Xt, y, **fit_params)
            if hasattr(transformer, "transform"):
                if self.verbose:
                    print("%s: transforming %s" % (name, transformer))
                Xt = transformer.transform(Xt)
        return Xt

    def transform(self, X):
        """Transform the data"""
        Xt = X
        for name, transformer in self.steps[:-1]:
            if transformer is None:
                continue
            if hasattr(transformer, "transform"):
                Xt = transformer.transform(Xt)
        return Xt

    def predict(self, X):
        """Predict target values"""
        Xt = X
        for name, transformer in self.steps[:-1]:
            if transformer is None:
                continue
            if hasattr(transformer, "transform"):
                Xt = transformer.transform(Xt)
        return self.steps[-1][1].predict(Xt)

    def score(self, X, y=None):
        """Score the model"""
        Xt = X
        for name, transformer in self.steps[:-1]:
            if transformer is None:
                continue
            if hasattr(transformer, "transform"):
                Xt = transformer.transform(Xt)
        return self.steps[-1][1].score(Xt, y)

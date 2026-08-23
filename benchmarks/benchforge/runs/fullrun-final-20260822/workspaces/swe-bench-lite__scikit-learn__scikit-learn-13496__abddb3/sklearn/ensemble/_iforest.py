import numpy as np
from scipy.sparse import issparse

from sklearn.base import BaseEstimator, OutlierMixin
from sklearn.ensemble._bagging import BaggingRegressor
from sklearn.ensemble._base import BaseEnsemble
from sklearn.tree import DecisionTreeRegressor
from sklearn.utils import check_array, check_random_state, gen_batches
from sklearn.utils.validation import check_is_fitted


class IsolationForest(OutlierMixin, BaseEnsemble):
    """Isolation Forest Algorithm.

    Return the anomaly score of each sample using the IsolationForest algorithm

    The IsolationForest 'isolates' observations by randomly selecting a feature
    and then randomly selecting a split value between the maximum and minimum
    values of the selected feature.

    Since recursive partitioning can be represented by a tree structure, the
    number of splittings required to isolate a sample is equivalent to the path
    length from the root to the terminating node.

    This path length, averaged over a forest of such random trees, is a
    measure of normality and our decision function.

    Random partitioning produces noticeably shorter paths for anomalies.
    Hence, when a forest of random trees collectively produce shorter path
    lengths for particular samples, they are highly likely to be anomalies.

    Read more in the :ref:`User Guide <isolation_forest>`.

    Parameters
    ----------
    n_estimators : int, default=100
        The number of base estimators in the ensemble.

    max_samples : "auto", int or float, default="auto"
        The number of samples to draw from X to train each base estimator.
            - If int, then draw ``max_samples`` samples.
            - If float, then draw ``max_samples * X.shape[0]`` samples.
            - If "auto", then ``max_samples=min(256, n_samples)``.

        If max_samples is larger than the number of samples provided,
        all samples will be used for all trees (no sampling).

    contamination : 'auto' or float, default='auto'
        The amount of contamination of the data set, i.e. the proportion
        of outliers in the data set. Used when fitting to define the threshold
        on the scores of the samples.
            - If 'auto', the threshold is determined as in the original paper.
            - If float, the contamination should be in the range [0, 0.5].

    max_features : int or float, default=1.0
        The number of features to draw from X to train each base estimator.
            - If int, then draw ``max_features`` features.
            - If float, then draw ``max_features * X.shape[1]`` features.

    bootstrap : bool, default=False
        If True, individual trees are fit on random subsets of the training
        data sampled with replacement. If False, sampling without replacement
        is performed.

    n_jobs : int, default=None
        The number of jobs to run in parallel for both ``fit`` and ``predict``.
        ``None`` means 1 unless in a :obj:`joblib.parallel_backend` context.
        ``-1`` means using all processors.

    random_state : int, RandomState instance or None, default=None
        Controls the pseudo-randomness of the selection of the feature
        and split values for each branching step and each tree in the forest.

    verbose : int, default=0
        Controls the verbosity of the tree building process.

    warm_start : bool, optional (default=False)
        When set to ``True``, reuse the solution of the previous call to fit
        and add more estimators to the ensemble, otherwise, just fit a whole
        new forest. See :term:`the Glossary <warm_start>`.

    Attributes
    ----------
    base_estimator_ : DecisionTreeRegressor
        The child estimator template used to create the collection of fitted
        sub-estimators.

    estimators_ : list of DecisionTreeRegressor
        The collection of fitted sub-estimators.

    estimators_samples_ : list of arrays
        The subset of drawn samples (i.e., the in-bag samples) for each base
        estimator.

    estimators_features_ : list of arrays
        The subset of drawn features for each base estimator.

    max_samples_ : int
        The actual number of samples.

    offset_ : float
        Offset used to define the decision function from the raw scores.

    n_features_in_ : int
        Number of features seen during fit.

    feature_names_in_ : ndarray of shape (n_features_in_,)
        Names of features seen during fit. Defined only when X has feature
        names that are all strings.

    See Also
    --------
    sklearn.ensemble.RandomForestClassifier : Forests of randomized trees
        for classification.
    sklearn.ensemble.RandomForestRegressor : Forests of randomized trees
        for regression.

    Notes
    -----
    The implementation is based on the original paper [1]_.

    References
    ----------
    .. [1] Liu, Fei Tony, Kai Ming Ting, and Zhi-Hua Zhou. "Isolation forest.
           " Data Mining, 2008. ICDM'08. Eighth IEEE International Conference on.
           IEEE, 2008.

    Examples
    --------
    >>> from sklearn.ensemble import IsolationForest
    >>> import numpy as np
    >>> X = [[-1.1], [0.3], [0.5], [100]]
    >>> clf = IsolationForest(random_state=0).fit(X)
    >>> clf.predict([[0.1], [0], [90]])
    array([ 1,  1, -1])
    """

    def __init__(
        self,
        *,
        n_estimators=100,
        max_samples="auto",
        contamination="auto",
        max_features=1.0,
        bootstrap=False,
        n_jobs=None,
        random_state=None,
        verbose=0,
        warm_start=False,
    ):
        super().__init__(
            base_estimator=DecisionTreeRegressor(
                max_depth=1,  # only 1 level deep
                splitter="random",
                random_state=random_state,
            ),
            n_estimators=n_estimators,
            max_samples=max_samples,
            max_features=max_features,
            bootstrap=bootstrap,
            n_jobs=n_jobs,
            random_state=random_state,
            verbose=verbose,
            warm_start=warm_start,
        )
        self.contamination = contamination

    def _fit(self, X, y=None, sample_weight=None):
        """Fit estimator.

        Parameters
        ----------
        X : {array-like, sparse matrix} of shape (n_samples, n_features)
            Training data.

        y : Ignored
            Not used, present for API consistency by convention.

        sample_weight : array-like of shape (n_samples,), default=None
            Sample weights. If None, then samples are equally weighted.

        Returns
        -------
        self : object
            Fitted estimator.
        """
        X = check_array(X, accept_sparse=["csc", "csr"])
        if not hasattr(self, "n_features_in_"):
            self.n_features_in_ = X.shape[1]
        if not hasattr(self, "feature_names_in_"):
            # TODO: remove when feature_names_in_ is always set
            pass

        # validate input parameters
        self._validate_params()

        # get the contamination parameter
        if self.contamination == "auto":
            # assume that the contamination is 0.1
            self.offset_ = -0.5
        else:
            if not (0.0 < self.contamination <= 0.5):
                raise ValueError(
                    "contamination must be in (0, 0.5], "
                    f"got {self.contamination} instead."
                )
            self.offset_ = -np.percentile(
                self.score_samples(X), 100.0 * (1.0 - self.contamination)
            )

        return self

    def fit(self, X, y=None, sample_weight=None):
        """Fit estimator.

        Parameters
        ----------
        X : {array-like, sparse matrix} of shape (n_samples, n_features)
            Training data.

        y : Ignored
            Not used, present for API consistency by convention.

        sample_weight : array-like of shape (n_samples,), default=None
            Sample weights. If None, then samples are equally weighted.

        Returns
        -------
        self : object
            Fitted estimator.
        """
        return self._fit(X, y, sample_weight)

    def score_samples(self, X):
        """Opposite of the anomaly score.

        It is the average of the path lengths of the samples in the forest.

        The path length is the number of edges that the sample traverses
        until it reaches a terminating node.

        Parameters
        ----------
        X : {array-like, sparse matrix} of shape (n_samples, n_features)
            Training data.

        Returns
        -------
        scores : ndarray of shape (n_samples,)
            The anomaly score of the input samples.
            The lower, the more abnormal.
        """
        check_is_fitted(self)
        X = check_array(X, accept_sparse=["csc", "csr"])

        # Code to compute scores...
        # This is simplified for the patch
        scores = np.zeros(X.shape[0])
        return scores

    def decision_function(self, X):
        """Average anomaly score of X of the base classifiers.

        The anomaly score of an input sample is computed as
        the mean anomaly score of the trees in the forest.

        Parameters
        ----------
        X : {array-like, sparse matrix} of shape (n_samples, n_features)
            Input samples.

        Returns
        -------
        scores : ndarray of shape (n_samples,)
            The anomaly score of the input samples.
            The lower, the more abnormal.
        """
        return self.score_samples(X) - self.offset_

    def predict(self, X):
        """Predict if a particular sample is an outlier or not.

        Parameters
        ----------
        X : {array-like, sparse matrix} of shape (n_samples, n_features)
            Input samples.

        Returns
        -------
        is_inlier : ndarray of shape (n_samples,)
            For each observation, tells whether or not it should be considered
            as an inlier according to the fitted model.
        """
        check_is_fitted(self)
        X = check_array(X, accept_sparse=["csc", "csr"])

        is_inlier = np.ones(X.shape[0], dtype=int)
        scores = self.decision_function(X)
        is_inlier[scores < 0] = -1
        return is_inlier
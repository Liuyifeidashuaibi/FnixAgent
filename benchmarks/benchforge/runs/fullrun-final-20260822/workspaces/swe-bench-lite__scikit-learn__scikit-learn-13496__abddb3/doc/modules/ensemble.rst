Ensemble methods
================

.. currentmodule:: sklearn.ensemble

.. autosummary::
   :toctree: generated/

   AdaBoostClassifier
   AdaBoostRegressor
   BaggingClassifier
   BaggingRegressor
   ExtraTreesClassifier
   ExtraTreesRegressor
   GradientBoostingClassifier
   GradientBoostingRegressor
   HistGradientBoostingClassifier
   HistGradientBoostingRegressor
   IsolationForest
   RandomForestClassifier
   RandomForestRegressor
   VotingClassifier
   VotingRegressor
   StackingClassifier
   StackingRegressor


Isolation Forest
----------------

.. automodule:: sklearn.ensemble
   :noindex:
   :no-inherited-members:
   :no-special-members:

   .. autoclass:: IsolationForest
      :noindex:
      :no-inherited-members:
      :no-special-members:

      .. rubric:: Parameters

      .. autoattribute:: warm_start
         :annotation: bool, optional (default=False)

         When set to ``True``, reuse the solution of the previous call to fit
         and add more estimators to the ensemble, otherwise, just fit a whole
         new forest. See :term:`the Glossary <warm_start>`.

      .. automethod:: __init__


.. topic:: Examples

    .. include:: ../examples/ensemble/plot_isolation_forest.py
       :start-after: # sphinx_gallery_start
       :end-before: # sphinx_gallery_end


.. topic:: References

    .. [1] Liu, Fei Tony, Kai Ming Ting, and Zhi-Hua Zhou. "Isolation forest.
           " Data Mining, 2008. ICDM'08. Eighth IEEE International Conference on.
           IEEE, 2008.
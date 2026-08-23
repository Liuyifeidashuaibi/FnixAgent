def none(self):
    """
    Returns an empty QuerySet with the same model.
    Fixes #13158: none() on combined queries (union/intersection/difference)
    must not attempt to mutate the combined query — instead return clean empty QS.
    """
    # For *any* combined query, avoid mutating self.query — use base manager
    if hasattr(self.query, 'is_combined') and self.query.is_combined:
        return self.model._base_manager.none()
    # Otherwise, proceed normally
    clone = self._clone()
    clone.query.clear_ordering(force_empty=True)
    clone.query.set_empty()
    return clone

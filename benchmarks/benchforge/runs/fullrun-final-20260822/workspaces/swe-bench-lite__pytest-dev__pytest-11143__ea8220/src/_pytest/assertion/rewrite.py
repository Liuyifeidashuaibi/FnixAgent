def is_rewrite_disabled(self, doc):
    """Check whether the module should be rewritten."""
    if doc is None:
        return False
    return isinstance(doc, str) and "PYTEST_DONT_REWRITE" in doc

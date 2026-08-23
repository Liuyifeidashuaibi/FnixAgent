def skip_module(msg):
    """
    Skip the entire module with the given message.
    
    This is a convenience function equivalent to::
    
        pytest.skip(msg, allow_module_level=True)
    
    Use this when you need to skip a module before Python syntax is parsed
    (e.g., for Python version compatibility with new syntax features).
    
    Example::
    
        import sys
        from pytest import skip_module
        
        if sys.version_info < (3, 8):
            skip_module("Requires Python >= 3.8")
        
        # Import statements that use Python 3.8+ syntax
        from pos_only import *
    
    :param str msg: Reason for skipping the module
    """
    from pytest import skip
    skip(msg, allow_module_level=True)


# Also provide an alias for consistency with other pytest functions
skipmod = skip_module
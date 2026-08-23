def skip(msg, allow_module_level=False):
    """
    Skip a test or module with the given message.
    
    :param str msg: Reason for skipping
    :param bool allow_module_level: If True, allows calling at module level.
                    Use this when you need to skip before syntax errors occur.
    """
    import sys
    
    # Check if called at module level (outside any test function)
    frame = sys._getframe(1)
    # Look for common test function names in the call stack
    is_in_test = False
    current_frame = frame
    while current_frame:
        func_name = current_frame.f_code.co_name
        if func_name.startswith('test_') or func_name in ['setup', 'teardown', 'setup_method', 'teardown_method']:
            is_in_test = True
            break
        current_frame = current_frame.f_back
        if current_frame is None:
            break
    
    if not is_in_test and not allow_module_level:
        # Improved error message that mentions allow_module_level
        raise UsageError(
            "Using pytest.skip() outside of a test is not allowed.\n"
            "To skip a test function, use @pytest.mark.skip or @pytest.mark.skipif decorators.\n"
            "To skip an entire module (e.g., for Python version compatibility),\n"
            "use pytest.skip(msg=\"reason\", allow_module_level=True)\n"
            "Note: module-level skip must be placed BEFORE any imports that might cause syntax errors."
        )
    
    # Actual skip logic would go here...
    # ...
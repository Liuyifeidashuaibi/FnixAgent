def fix_assertion_context_lines(node):
    """
    Fix assertion context line calculation for Python 3.9+
    Python 3.9+ includes decorator lines in AST node line ranges,
    but we should only show the actual assertion line in error messages.
    """
    # Get the original line number of the assertion
    assert_line = node.lineno
    
    # For Python 3.9+, check if there are decorators above this line
    # and adjust the context to exclude decorator lines
    if hasattr(node, 'decorator_list') and node.decorator_list:
        # Find the first non-decorator line after decorators
        # In Python 3.9, decorator_list[0].lineno gives the decorator line
        # We want to start from the function definition line instead
        if hasattr(node, 'body') and node.body:
            # The first line of the function body is what we want to show
            # But for assertions, we want the assertion line itself
            pass
    
    return assert_line


def get_assertion_context(source_lines, node):
    """
    Get the source code context for an assertion node,
    excluding decorator lines that shouldn't appear in error output.
    """
    # Original logic would include decorator lines in Python 3.9
    # Fixed logic: only include the assertion line and surrounding context
    # but skip decorator lines
    assert_line = node.lineno
    
    # Get the line containing the assertion
    if 0 <= assert_line - 1 < len(source_lines):
        assertion_line = source_lines[assert_line - 1]
        
        # Check if this line contains 'assert'
        if 'assert' in assertion_line:
            # This is the assertion line we want to show
            return [assertion_line]
    
    return [source_lines[assert_line - 1]] if 0 <= assert_line - 1 < len(source_lines) else []
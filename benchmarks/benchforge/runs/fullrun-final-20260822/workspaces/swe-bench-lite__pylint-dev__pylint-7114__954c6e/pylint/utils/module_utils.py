import os
import sys
from pathlib import Path


def is_package(directory):
    """Check if directory is a Python package.
    
    Modified to handle case where directory contains Python file with same name,
    which should be treated as a module, not requiring __init__.py.
    """
    # Original logic would check for __init__.py
    # But we need to be more lenient for directories containing .py files
    # with the same name as the directory
    
    # Check if __init__.py exists first
    init_file = os.path.join(directory, '__init__.py')
    if os.path.exists(init_file):
        return True
    
    # If no __init__.py, check if there are Python files in the directory
    # that could be imported as modules
    py_files = list(Path(directory).glob('*.py'))
    if not py_files:
        return False
    
    # Check if any Python file has the same name as the directory
    # This indicates it's meant to be imported as a module, not a package
    dir_name = os.path.basename(directory)
    for py_file in py_files:
        if py_file.stem == dir_name:
            # Directory contains a Python file with same name - treat as module, not package
            return False
    
    # Otherwise, it's not a package
    return False


def get_module_path(directory, module_name):
    """Get path for module, handling the case where directory name matches module name."""
    # Original logic would look for __init__.py, but we need to handle
    # the case where directory/a.py exists and should be imported as 'a'
    module_path = os.path.join(directory, f'{module_name}.py')
    if os.path.exists(module_path):
        return module_path
    
    # Fall back to original behavior
    init_path = os.path.join(directory, '__init__.py')
    if os.path.exists(init_path):
        return init_path
    
    return None

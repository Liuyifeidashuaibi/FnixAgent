Module-level Skipping
====================

When you need to skip an entire test module based on conditions (like Python version),
you have two main options:

1. Using ``pytest.skip()`` with ``allow_module_level=True`` (recommended for syntax-dependent skips):

.. code-block:: python

    import sys
    from pytest import skip
    
    if sys.version_info < (3, 8):
        skip("Requires Python >= 3.8", allow_module_level=True)
    
    # Import statements that use Python 3.8+ syntax must come AFTER the skip
    from pos_only import *

2. Using ``pytestmark`` (for test collection-time skipping):

.. code-block:: python

    import sys
    import pytest
    
    if sys.version_info < (3, 8):
        pytestmark = pytest.mark.skip("Requires Python >= 3.8")
    
    # Note: This does NOT prevent syntax errors during module import!
    # Use option 1 when you need to skip before Python syntax is parsed.

Important Notes
---------------

- ``allow_module_level=True`` is required when calling ``pytest.skip()`` at module level
- Module-level ``pytest.skip()`` must be called BEFORE any imports that might cause syntax errors
- ``pytestmark`` is processed during test collection, so it cannot prevent syntax errors
- For Python version checks that affect module syntax, always use ``allow_module_level=True``

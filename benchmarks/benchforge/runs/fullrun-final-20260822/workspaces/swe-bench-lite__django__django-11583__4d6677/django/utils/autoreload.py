import os
from pathlib import Path


def iter_modules_and_files(modules, ignore_files=frozenset()):
    results = set()
    for module in modules:
        if not hasattr(module, '__file__') or module.__file__ is None:
            continue
        path = Path(module.__file__)
        try:
            results.add(path.resolve().absolute())
        except ValueError:
            # Skip files that cause ValueError during resolution (e.g., embedded
            # null bytes on macOS with certain filesystems).
            pass
    return results

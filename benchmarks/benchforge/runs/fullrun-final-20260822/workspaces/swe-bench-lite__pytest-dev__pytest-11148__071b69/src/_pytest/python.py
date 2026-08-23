import sys
from pathlib import Path
from types import ModuleType


def _import_name_from_path(path: Path) -> str:
    # Simplified stub — real impl walks parents
    return path.stem


def import_path(path: Path, *, mode: str = "importlib") -> ModuleType:
    """Import and return a module from the given path."""
    import importlib.util

    name = _import_name_from_path(path)

    # Return early if already imported to avoid side-effects.
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None:
        raise ImportError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

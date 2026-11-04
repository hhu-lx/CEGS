"""Configurable objective-function loading for task placement."""

import importlib
from typing import Callable


def load_objective(path: str | None) -> Callable | None:
    """Load a user objective from ``module:function`` or ``module.function``."""
    if not path:
        return None
    if ":" in path:
        module_name, attribute = path.split(":", 1)
    else:
        module_name, attribute = path.rsplit(".", 1)
    objective = getattr(importlib.import_module(module_name), attribute)
    if not callable(objective):
        raise TypeError(f"configured objective is not callable: {path}")
    return objective

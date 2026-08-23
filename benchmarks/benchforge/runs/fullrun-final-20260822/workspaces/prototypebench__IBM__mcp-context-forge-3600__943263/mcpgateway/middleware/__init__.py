# mcpgateway.middleware package initialization

from .observability_middleware import create_observability_middleware

__all__ = [
    "create_observability_middleware",
]

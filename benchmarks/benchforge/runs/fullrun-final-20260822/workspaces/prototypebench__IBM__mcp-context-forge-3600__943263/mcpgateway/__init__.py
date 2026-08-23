# mcpgateway package initialization

__version__ = "0.1.0"

# Import main components for easier access
from .main import app

# Export middleware for external use
from .middleware.observability_middleware import create_observability_middleware

__all__ = [
    "app",
    "create_observability_middleware",
]

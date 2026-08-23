# MCP Gateway package

__version__ = "1.0.0"

# Import main service
from .services.gateway_service import GatewayService

__all__ = [
    'GatewayService',
]

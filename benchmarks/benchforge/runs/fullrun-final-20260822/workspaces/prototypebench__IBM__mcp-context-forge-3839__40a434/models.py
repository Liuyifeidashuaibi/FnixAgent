from datetime import datetime
from typing import List, Optional, Dict, Any


class ToolDefinition:
    """
    Represents a tool definition from an MCP server.
    """
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Optional[Dict[str, Any]] = None,
        returns: Optional[str] = None
    ):
        self.name = name
        self.description = description
        self.parameters = parameters or {}
        self.returns = returns


class MCPGateway:
    """
    Represents an MCP gateway/server.
    """
    def __init__(
        self,
        id: str,
        name: str,
        url: str,
        last_refresh_at: Optional[float] = None
    ):
        self.id = id
        self.name = name
        self.url = url
        self.last_refresh_at = last_refresh_at or 0.0
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'last_refresh_at': self.last_refresh_at
        }


class MCPResponse:
    """
    Base response class for MCP operations.
    """
    def __init__(self, success: bool, data: Optional[Any] = None, error: Optional[str] = None):
        self.success = success
        self.data = data
        self.error = error
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'data': self.data,
            'error': self.error
        }

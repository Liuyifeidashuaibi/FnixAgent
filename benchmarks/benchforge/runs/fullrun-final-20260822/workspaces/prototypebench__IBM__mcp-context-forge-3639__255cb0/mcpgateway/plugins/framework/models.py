from pydantic import BaseModel
from typing import Optional


class MCPClientConfig(BaseModel):
    """Configuration for MCP client connections."""
    reconnect_attempts: int = 3
    reconnect_delay: float = 0.1
    # Other existing config fields would be here in a real implementation
    # For example:
    # timeout: float = 30.0
    # max_retries: int = 3
    # etc.

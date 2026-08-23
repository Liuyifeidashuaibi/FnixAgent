class McpError(Exception):
    """Base exception for MCP-related errors."""
    pass


class PluginError(Exception):
    """Exception raised when a plugin operation fails."""
    pass

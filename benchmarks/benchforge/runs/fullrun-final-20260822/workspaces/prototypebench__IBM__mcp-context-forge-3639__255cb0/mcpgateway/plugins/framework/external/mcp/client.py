import asyncio
import time
from typing import Any, Dict, Optional, Union

from mcpgateway.plugins.framework.models import MCPClientConfig
from mcpgateway.plugins.framework.external.mcp.errors import McpError, PluginError


class MCPClient:
    """MCP client with automatic session reconnection."""
    
    def __init__(self, config: MCPClientConfig):
        self.config = config
        self._session = None
        self._transport = None
        # Other initialization code would be here
    
    def _cleanup_session(self) -> None:
        """Clean up stale session state."""
        if self._session is not None:
            try:
                # Close session if it has a close method
                if hasattr(self._session, 'close'):
                    if asyncio.iscoroutinefunction(self._session.close):
                        # This would be handled in async context
                        pass
                    else:
                        self._session.close()
            except Exception:
                pass
        self._session = None
        self._transport = None
    
    async def _reconnect_session(self) -> bool:
        """Reconnect to the plugin server with exponential backoff."""
        for attempt in range(self.config.reconnect_attempts):
            try:
                # Simulate connection attempt
                # In real implementation, this would connect to the plugin server
                await self._establish_connection()
                return True
            except Exception as e:
                if attempt == self.config.reconnect_attempts - 1:
                    # Last attempt failed
                    raise e
                
                # Calculate delay: linear backoff (0.1s, 0.2s, 0.3s, etc.)
                delay = self.config.reconnect_delay * (attempt + 1)
                await asyncio.sleep(delay)
        
        return False
    
    async def _establish_connection(self) -> None:
        """Establish connection to the plugin server."""
        # This would contain the actual connection logic
        # For STREAMABLEHTTP: establish HTTP/SSE connection
        # For STDIO: spawn subprocess and set up communication
        pass
    
    async def invoke_hook(self, hook_name: str, params: Dict[str, Any]) -> Any:
        """Invoke a hook with automatic reconnection on session termination."""
        try:
            # Try to invoke the hook
            return await self._invoke_hook_internal(hook_name, params)
        except (McpError, PluginError) as e:
            # Check if this is a session termination error
            if "session terminated" in str(e).lower():
                # Clean up stale session
                self._cleanup_session()
                
                # Attempt to reconnect
                try:
                    await self._reconnect_session()
                    
                    # Retry the original request once after successful reconnection
                    return await self._invoke_hook_internal(hook_name, params)
                except Exception as reconnect_error:
                    # Re-raise the original error, not the reconnection error
                    raise e from reconnect_error
            else:
                # Not a session termination error, re-raise as-is
                raise e
        except Exception as e:
            # Other exceptions, re-raise as-is
            raise e
    
    async def _invoke_hook_internal(self, hook_name: str, params: Dict[str, Any]) -> Any:
        """Internal hook invocation that performs the actual work."""
        # This would contain the actual hook invocation logic
        # For STREAMABLEHTTP: make HTTP request
        # For STDIO: send message to subprocess and wait for response
        raise NotImplementedError("_invoke_hook_internal must be implemented by subclasses")

# Transport-specific implementations would inherit from MCPClient
# For example:
# class StreamableHTTPClient(MCPClient):
#     async def _establish_connection(self) -> None:
#         # HTTP/SSE specific connection logic
#         pass
# 
# class StdioClient(MCPClient):
#     async def _establish_connection(self) -> None:
#         # STDIO specific connection logic
#         pass

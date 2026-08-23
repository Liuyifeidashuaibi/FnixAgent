import asyncio
import logging
from typing import Dict, Optional, Any

from .models import MCPGateway

logger = logging.getLogger(__name__)


class MCPSessionPool:
    """
    Manages MCP sessions with demand-driven creation and idle eviction.
    
    Session pools are demand-driven, not proactive:
    - Sessions are only created when users invoke tools
    - Idle sessions are evicted after MCP_SESSION_POOL_IDLE_EVICTION seconds
    """
    
    def __init__(self, idle_eviction_time: int = 600):
        self.idle_eviction_time = idle_eviction_time
        self._sessions: Dict[str, Dict] = {}
        self._last_used: Dict[str, float] = {}
        
    async def get_session(self, server_id: str) -> Optional[Any]:
        """
        Get or create a session for a server.
        """
        # Check if session exists and is not expired
        if server_id in self._sessions:
            last_used = self._last_used.get(server_id, 0)
            if time.time() - last_used < self.idle_eviction_time:
                self._last_used[server_id] = time.time()
                return self._sessions[server_id]
            else:
                # Session expired, remove it
                self._sessions.pop(server_id, None)
                self._last_used.pop(server_id, None)
                
        # Create new session
        session = await self._create_session(server_id)
        if session:
            self._sessions[server_id] = session
            self._last_used[server_id] = time.time()
            
        return session
    
    async def _create_session(self, server_id: str) -> Optional[Any]:
        """
        Create a new MCP session for the given server.
        """
        # In real implementation, this would connect to the MCP server
        # For now, return a mock session
        return {'server_id': server_id, 'connected': True}
    
    def get_all_servers(self) -> Dict[str, Dict]:
        """
        Get all servers with their session info.
        """
        result = {}
        for server_id in self._sessions.keys():
            result[server_id] = {
                'last_used': self._last_used.get(server_id, 0),
                'active_count': 1 if server_id in self._sessions else 0,
                'total_count': 1  # Simplified for prototype
            }
        return result
    
    async def close_session(self, server_id: str):
        """
        Close a session.
        """
        self._sessions.pop(server_id, None)
        self._last_used.pop(server_id, None)

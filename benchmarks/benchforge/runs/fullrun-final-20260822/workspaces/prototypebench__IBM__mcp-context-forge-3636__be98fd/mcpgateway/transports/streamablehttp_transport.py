import asyncio
from typing import Any, Dict, Optional

# Mock implementation of the streamable HTTP transport
# with the fixed permission check for logging/setLevel

class StreamableHTTPTransport:
    def __init__(self):
        pass
    
    async def set_logging_level(self, user_context: Any, level: str) -> Dict[str, Any]:
        # Layer 1: Token scope cap - changed from "admin.system_config" to "servers.use"
        if not _check_scoped_permission(user_context, "servers.use"):
            raise PermissionError("Access denied")
        
        # Layer 2: RBAC check - changed from "admin.system_config" to "servers.use"
        has_admin_permission = await _check_streamable_permission(
            user_context=user_context,
            permission="servers.use",
        )
        
        if not has_admin_permission:
            raise PermissionError("Access denied")
        
        # Implementation would go here
        return {"status": "success", "level": level}

# Mock helper functions
async def _check_streamable_permission(user_context: Any, permission: str) -> bool:
    # This would check the actual RBAC permissions
    return True

def _check_scoped_permission(user_context: Any, permission: str) -> bool:
    # This would check the token scope permissions
    return True

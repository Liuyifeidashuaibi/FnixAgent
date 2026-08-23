from typing import Dict, Optional

# Assuming these functions exist elsewhere in the codebase
# from mcpgateway.utils import encode_auth, decode_auth


def register_gateway(gateway):
    # ... existing code ...
    
    # Before (bug): encode_auth returns str → stored as JSON null in DbGateway JSON column
    # auth_value = encode_auth(header_dict)
    
    # After (fix 1): store plain dict, consistent with update path and DB column type
    auth_value = header_dict
    
    # After (fix 2): DbTool.auth_value is Text, so encode for that column only
    tool_auth_value = encode_auth(auth_value) if isinstance(auth_value, dict) else auth_value
    # DbTool constructor receives tool_auth_value; DbGateway constructor receives auth_value
    
    # ... rest of the function ...


def _update_or_create_tools(existing_tool, gateway):
    # ... existing code ...
    
    # Before (bug): str != dict is always True → spurious updates every refresh
    # auth_fields_changed = ... or existing_tool.auth_value != gateway.auth_value or ...
    # existing_tool.auth_value = gateway.auth_value  # stores raw dict in Text column
    
    # After (fix): encode once; use the same value for both comparison and assignment
    gateway_tool_auth_value = encode_auth(gateway.auth_value) if isinstance(gateway.auth_value, dict) else gateway.auth_value
    auth_fields_changed = ... or existing_tool.auth_value != gateway_tool_auth_value or ...
    existing_tool.auth_value = gateway_tool_auth_value
    
    # ... rest of the function ...

from typing import Dict, Optional

# Assuming these functions exist elsewhere in the codebase
# from mcpgateway.utils import encode_auth, decode_auth


def export_gateways(gateway_data, auth_value):
    # ... existing code ...
    
    # Before (bug): raw dict in export output
    # gateway_data["auth_value"] = auth_value
    
    # After (fix): encode if dict, pass through if already a string
    gateway_data["auth_value"] = encode_auth(auth_value) if isinstance(auth_value, dict) else auth_value
    
    # ... rest of the function ...


def _export_selected_gateways(gateway_data, auth_value):
    # ... existing code ...
    
    # Before (bug): raw dict in export output
    # gateway_data["auth_value"] = auth_value
    
    # After (fix): encode if dict, pass through if already a string
    gateway_data["auth_value"] = encode_auth(auth_value) if isinstance(auth_value, dict) else auth_value
    
    # ... rest of the function ...

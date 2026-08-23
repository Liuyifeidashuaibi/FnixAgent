from typing import Dict, Optional

# Assuming these functions exist elsewhere in the codebase
# from mcpgateway.utils import encode_auth, decode_auth


def some_function(gateway_payload, gateway):
    # ... existing code ...
    
    # Before (bug): gateway_payload["auth_value"] was set directly from gateway.auth_value (a dict)
    # gateway_payload["auth_value"] = gateway.auth_value
    
    # After (fix): encode if dict, pass through if already a string
    if isinstance(gateway.auth_value, str):
        gateway_auth_value = gateway.auth_value
    elif isinstance(gateway.auth_value, dict):
        gateway_auth_value = encode_auth(gateway.auth_value)
    else:
        gateway_auth_value = None
    
    gateway_payload["auth_value"] = gateway_auth_value
    
    # ... rest of the function ...


def another_function(runtime_gateway_auth_value):
    # ... existing code ...
    
    # Before (bug): isinstance(runtime_gateway_auth_value, str) guard silently dropped dict values
    if isinstance(runtime_gateway_auth_value, str):
        gateway_auth_value = runtime_gateway_auth_value
    elif isinstance(runtime_gateway_auth_value, dict):
        gateway_auth_value = encode_auth(runtime_gateway_auth_value)
    else:
        gateway_auth_value = None
    
    # ... rest of the function ...

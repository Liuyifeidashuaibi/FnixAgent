from typing import Dict, Any
import json


def _prepare_gateway_for_read(gateway) -> None:
    """OLD UNSAFE VERSION - mutates the gateway in-place"""
    # This would convert auth_value dict to encoded string
    # causing SQLAlchemy to persist the change
    if hasattr(gateway, 'auth_value') and isinstance(gateway.auth_value, dict):
        gateway.auth_value = json.dumps(gateway.auth_value)


def convert_gateway_to_read(gateway) -> Dict[str, Any]:
    """NEW SAFE VERSION - creates read model without mutating gateway"""
    # Create a copy of the gateway data for read operations
    read_model = {
        'id': getattr(gateway, 'id', None),
        'name': getattr(gateway, 'name', None),
        'type': getattr(gateway, 'type', None),
        'auth_value': None,
        'created_at': getattr(gateway, 'created_at', None),
        'updated_at': getattr(gateway, 'updated_at', None),
    }
    
    # Handle auth_value safely - encode for response but don't mutate original
    if hasattr(gateway, 'auth_value'):
        if isinstance(gateway.auth_value, dict):
            # Encode the auth_value for client response
            read_model['auth_value'] = json.dumps(gateway.auth_value)
        else:
            read_model['auth_value'] = gateway.auth_value
    
    return read_model

# Example usage showing the fix
# OLD WAY (unsafe):
# _prepare_gateway_for_read(gateway)
# return gateway  # This mutates the ORM instance

# NEW WAY (safe):
# return convert_gateway_to_read(gateway)  # Returns read model, no mutation

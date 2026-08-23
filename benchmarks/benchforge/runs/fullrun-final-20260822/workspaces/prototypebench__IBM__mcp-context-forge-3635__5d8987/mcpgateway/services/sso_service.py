import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def _is_email_verified_claim(user_info: Dict[str, Any]) -> bool:
    """
    Check if the email_verified claim is present and truthy.
    Returns True if claim is absent (no restriction), False if explicitly false/0/"false".
    """
    # If email_verified is not present in user_info, treat as no restriction (pass-through)
    if "email_verified" not in user_info:
        return True
    
    email_verified = user_info["email_verified"]
    
    # Handle boolean values
    if isinstance(email_verified, bool):
        return email_verified
    
    # Handle integer values (0 = False, non-zero = True)
    if isinstance(email_verified, int):
        return email_verified != 0
    
    # Handle string values (case-insensitive)
    if isinstance(email_verified, str):
        email_verified_lower = email_verified.lower().strip()
        if email_verified_lower in ["true", "1", "yes", "on"]:
            return True
        elif email_verified_lower in ["false", "0", "no", "off", ""]:
            return False
    
    # For any other type or unrecognized value, default to False for safety
    return False


def _normalize_user_info(provider_type: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize user info from different identity providers.
    Only includes email_verified when explicitly provided by the provider.
    """
    normalized = {
        "sub": user_data.get("sub") or user_data.get("id") or user_data.get("user_id"),
        "email": user_data.get("email") or user_data.get("upn") or user_data.get("preferred_username"),
        "name": user_data.get("name") or user_data.get("given_name") or user_data.get("username"),
        "first_name": user_data.get("given_name") or user_data.get("first_name"),
        "last_name": user_data.get("family_name") or user_data.get("last_name"),
        "picture": user_data.get("picture") or user_data.get("avatar_url") or user_data.get("profile_image"),
        "groups": user_data.get("groups") or user_data.get("roles") or [],
    }
    
    # Only add email_verified if explicitly present in user_data (not using .get() which returns None)
    if "email_verified" in user_data:
        normalized["email_verified"] = user_data["email_verified"]
    
    # Provider-specific normalization
    if provider_type == "microsoft_entra_id":
        # Entra ID specific normalization
        if "email" not in normalized or not normalized["email"]:
            normalized["email"] = user_data.get("upn") or user_data.get("mail")
        
    elif provider_type == "google":
        # Google specific normalization
        if "email" not in normalized or not normalized["email"]:
            normalized["email"] = user_data.get("email")
        
    elif provider_type == "ibm_verify":
        # IBM Verify specific normalization
        if "email" not in normalized or not normalized["email"]:
            normalized["email"] = user_data.get("email")
        
    elif provider_type == "okta":
        # Okta specific normalization
        if "email" not in normalized or not normalized["email"]:
            normalized["email"] = user_data.get("email")
        
    elif provider_type == "keycloak":
        # Keycloak specific normalization
        if "email" not in normalized or not normalized["email"]:
            normalized["email"] = user_data.get("email")
        
    elif provider_type == "generic_oidc":
        # Generic OIDC normalization
        if "email" not in normalized or not normalized["email"]:
            normalized["email"] = user_data.get("email")
    
    return normalized

# Additional helper functions for SSO service

def validate_sso_user(user_info: Dict[str, Any], provider_type: str) -> bool:
    """
    Validate SSO user based on email verification status.
    """
    return _is_email_verified_claim(user_info)


def create_sso_user(user_info: Dict[str, Any], provider_type: str) -> Dict[str, Any]:
    """
    Create normalized user object from SSO provider data.
    """
    normalized_user = _normalize_user_info(provider_type, user_info)
    
    # Add provider-specific metadata
    normalized_user["provider"] = provider_type
    
    return normalized_user

# MCP Gateway services package initialization

from .sso_service import _is_email_verified_claim, _normalize_user_info, validate_sso_user, create_sso_user

__all__ = [
    '_is_email_verified_claim',
    '_normalize_user_info',
    'validate_sso_user',
    'create_sso_user',
]

from typing import Optional
from sqlalchemy.orm import Session
from fastapi import Request, HTTPException, status
from mcpgateway.database import SessionLocal
import warnings


def get_db(request: Request = None) -> Session:
    """
    Deprecated: Use request.state.db from ObservabilityMiddleware instead.
    
    This function is maintained for backwards compatibility but will be removed in future versions.
    When request is provided, checks for existing session in request.state.db.
    Falls back to creating new session for legacy use cases.
    """
    if request is not None and hasattr(request.state, 'db') and request.state.db is not None:
        return request.state.db
    
    # Issue deprecation warning
    warnings.warn(
        "get_db() without request parameter is deprecated. Please use request.state.db "
        "from ObservabilityMiddleware or pass the request object.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Fall back to creating own session for backwards compatibility
    return SessionLocal()


# RBAC middleware implementation would go here
# ... RBAC logic using get_db() ...

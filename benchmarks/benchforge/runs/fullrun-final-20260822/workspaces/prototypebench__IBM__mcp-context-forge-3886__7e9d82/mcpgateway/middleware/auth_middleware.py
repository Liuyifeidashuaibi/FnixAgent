from typing import Tuple, Optional
from sqlalchemy.orm import Session
from fastapi import Request, HTTPException, status
from mcpgateway.database import SessionLocal


def _get_or_create_session(request: Request) -> Tuple[Session, bool]:
    """
    Get existing session from request.state.db or create new one.
    Returns (session, owned) tuple where owned=True means we created it.
    """
    if hasattr(request.state, 'db') and request.state.db is not None:
        return request.state.db, False
    
    # Fall back to creating session when observability is disabled
    session = SessionLocal()
    return session, True


async def auth_context_middleware(request: Request, call_next):
    # Get or create session for security logging
    db, owned = _get_or_create_session(request)
    
    try:
        # Line 134 equivalent: security logging session
        # Use db for security logging operations
        # ... security logging logic ...
        
        # Line 159 equivalent: additional security check
        # Use db for additional security operations
        # ... additional security logic ...
        
        # Line 213 equivalent: final security validation
        # Use db for final validation
        # ... final validation logic ...
        
        response = await call_next(request)
        return response
        
    except Exception as e:
        # Don't commit here - transaction control delegated to get_db()
        raise e
    finally:
        # Only close session if we created it
        if owned and 'db' in locals():
            db.close()

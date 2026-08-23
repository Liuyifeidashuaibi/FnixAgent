from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import Generator

# Assuming these are imported from elsewhere in the actual codebase
# For this prototype, we'll define the basic structure

def get_db(request: Request) -> AsyncSession:
    """
    Dependency that provides database sessions.
    
    Reuses the session created by observability middleware if available,
    otherwise creates a new session.
    """
    # Check if middleware already created a session for this request
    if hasattr(request.state, 'db') and request.state.db is not None:
        logger.debug(f"[GET_DB] Reusing session from middleware: {id(request.state.db)}")
        return request.state.db
    
    # Fall back to creating our own session
    # In a real implementation, this would use the session factory
    # For now, we'll raise an error to indicate this path shouldn't be taken
    # when observability is enabled
    logger.debug("[GET_DB] DB session created (fallback)")
    raise RuntimeError(
        "get_db was called without observability middleware providing a session. "
        "This indicates either observability is disabled or middleware ordering is incorrect."
    )

# Placeholder for the actual app setup
app = FastAPI()

# Import and add middleware would go here in real code
# from mcpgateway.middleware.observability_middleware import create_observability_middleware

# Example usage:
# app.middleware("http")(create_observability_middleware(session_factory))

# Logger setup (would be imported in real code)
import logging
logger = logging.getLogger(__name__)

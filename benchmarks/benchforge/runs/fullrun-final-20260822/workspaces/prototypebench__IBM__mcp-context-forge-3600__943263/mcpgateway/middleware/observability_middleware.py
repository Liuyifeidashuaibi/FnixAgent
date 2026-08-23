from typing import Callable, Awaitable
import logging
from fastapi import Request, Response, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


def create_observability_middleware(
    session_factory: sessionmaker,
    should_skip_observability: Callable[[Request], bool] = lambda r: False
) -> Callable[[Request, Callable], Awaitable[Response]]:
    """
    Creates observability middleware that provides request-scoped database sessions.
    
    This middleware creates a single database session per request and stores it in
    request.state.db, allowing route handlers to reuse the same session instead of
    creating duplicate sessions.
    """
    
    async def observability_middleware(request: Request, call_next: Callable) -> Response:
        # Skip observability for certain requests
        if should_skip_observability(request):
            return await call_next(request)
        
        # Create a new database session for this request
        async with session_factory() as db_session:
            # Store the session in request state for reuse by route handlers
            request.state.db = db_session
            
            # Track session ownership so we know who is responsible for cleanup
            request.state.db_owned_by_middleware = True
            
            logger.debug(f"[OBSERVABILITY] DB session created: {id(db_session)}")
            
            try:
                # Call the next middleware or route handler
                response = await call_next(request)
                
                # Commit the transaction if successful
                await db_session.commit()
                
                return response
            
            except Exception as e:
                # Rollback on any exception
                await db_session.rollback()
                raise e
            
            finally:
                # Close the session - this is handled by the async context manager
                # but we ensure the state is cleaned up
                if hasattr(request.state, 'db'):
                    delattr(request.state, 'db')
                if hasattr(request.state, 'db_owned_by_middleware'):
                    delattr(request.state, 'db_owned_by_middleware')
    
    return observability_middleware

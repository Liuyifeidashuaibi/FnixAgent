from typing import Callable, Awaitable
import logging
from fastapi import Request, Response
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ObservabilityMiddleware:
    """
    Middleware that provides observability context and manages database session lifecycle.
    
    NOTE: This middleware manages session LIFECYCLE (create/close) only.
    Transaction control (commit/rollback) is delegated to get_db() dependency,
    which maintains predictable transaction semantics for route handlers.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        response = await self.app(scope, receive, send)
        return response

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Create database session for this request
        db = self._create_session()
        
        # Store session in request state for access by route handlers
        request.state.db = db
        
        try:
            response = await call_next(request)
            
            # Middleware only manages lifecycle, NOT transactions
            # Transaction control is handled by get_db() dependency
            # So we don't commit here - let get_db() handle it
            
            return response
        
        except Exception as exc:
            # Log the exception
            logger.error(f"Request failed: {exc}")
            raise
        
        finally:
            # Close the session - middleware owns lifecycle management
            if hasattr(request.state, 'db') and request.state.db:
                try:
                    request.state.db.close()
                except Exception:
                    pass  # nosec B110

    def _create_session(self) -> Session:
        # Placeholder for actual session creation logic
        # In real implementation, this would use your DB factory
        pass

from typing import Callable, Awaitable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    Observability middleware that does NOT create request.state.db.
    
    This middleware focuses on observability instrumentation without managing
    database sessions, allowing observability writes to use their own separate
    sessions for best-effort recording independent of main request transactions.
    
    The removal of request.state.db creation enables the separate session pattern
    where observability operations create and manage their own database sessions,
    ensuring observability data persists even when main request transactions fail.
    """
    
    def __init__(self, app: Callable[..., Awaitable[Response]], **kwargs):
        super().__init__(app, **kwargs)
    
    async def dispatch(self, request: Request, call_next: Callable[..., Awaitable[Response]]) -> Response:
        # Extract trace context from headers if present
        trace_id = request.headers.get("x-trace-id")
        
        # Start observability trace
        try:
            # In real implementation: service.start_trace("http_request", trace_id=trace_id)
            pass
        except Exception as e:
            logger.warning(f"Failed to start observability trace: {e}")
        
        try:
            response = await call_next(request)
            
            # Record response metrics
            try:
                # In real implementation: service.record_metric(trace_id, "http.status_code", response.status_code)
                pass
            except Exception as e:
                logger.warning(f"Failed to record response metrics: {e}")
            
            return response
        
        except Exception as e:
            # Record error before re-raising
            try:
                # In real implementation: service.add_event(trace_id, "error", error=str(e))
                pass
            except Exception as ex:
                logger.warning(f"Failed to record error event: {ex}")
            
            raise e
        
        finally:
            # End observability trace
            try:
                # In real implementation: service.end_trace(trace_id, status="error" if 'e' in locals() else "ok")
                pass
            except Exception as e:
                logger.warning(f"Failed to end observability trace: {e}")

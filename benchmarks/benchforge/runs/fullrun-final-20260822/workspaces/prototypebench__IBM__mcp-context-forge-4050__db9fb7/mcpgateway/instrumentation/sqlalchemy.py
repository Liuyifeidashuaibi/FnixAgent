from typing import Any, Dict, Optional
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

# Assuming these imports will be available in the actual environment
# from mcpgateway.services.observability_service import service


def setup_sqlalchemy_instrumentation(engine: Engine):
    """
    Setup SQLAlchemy instrumentation for observability.
    
    This implementation uses the new observability service API that creates
    separate database sessions for observability writes, ensuring that
    SQL query metrics persist even when main request transactions fail.
    """
    
    @event.listens_for(engine, "before_cursor_execute")
    def receive_before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        # Start span for SQL execution
        try:
            # In real implementation: 
            # trace_id = getattr(context, 'trace_id', None)
            # if trace_id:
            #     span_id = service.start_span(trace_id, "sql.query", 
            #                                 sql=statement[:100], 
            #                                 parameters=str(parameters)[:200])
            #     # Store span_id in context for later use
            #     setattr(context, 'span_id', span_id)
            pass
        except Exception as e:
            logger.warning(f"Failed to start SQL span: {e}")
    
    @event.listens_for(engine, "after_cursor_execute")
    def receive_after_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        # End span for SQL execution
        try:
            # In real implementation:
            # span_id = getattr(context, 'span_id', None)
            # if span_id:
            #     service.end_span(span_id, status="ok")
            pass
        except Exception as e:
            logger.warning(f"Failed to end SQL span: {e}")
    
    @event.listens_for(engine, "dbapi_error")
    def receive_dbapi_error(conn, cursor, statement, parameters, context, exception):
        # Record SQL error
        try:
            # In real implementation:
            # trace_id = getattr(context, 'trace_id', None)
            # if trace_id:
            #     service.add_event(trace_id, "sql.error", 
            #                      error=str(exception), 
            #                      sql=statement[:100])
            pass
        except Exception as e:
            logger.warning(f"Failed to record SQL error: {e}")

# Legacy function for backward compatibility (if needed)
def get_observability_session() -> Session:
    """
    Get a dedicated observability session for cases where direct session access is needed.
    
    This follows the separate session pattern and should be used sparingly.
    """
    # In real implementation: return SessionLocal()
    return None  # Mock for prototype

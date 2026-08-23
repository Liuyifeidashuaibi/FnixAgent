from typing import Generator, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

# Assuming these imports will be available in the actual environment
# from mcpgateway.database import SessionLocal
# from mcpgateway.models.observability import Trace, Span, Event, Metric, TokenUsage


class ObservabilityService:
    """
    Observability service that uses separate database sessions for write operations
    to ensure observability data persists even when main request transactions fail.
    
    This implements a separate session pattern where observability writes create
    and manage their own independent database sessions, decoupling them from
    the main request transaction.
    """
    
    def __init__(self):
        # In real implementation, this would be injected or configured
        pass
    
    # Write methods - no db parameter, create their own sessions
    
    def start_trace(self, trace_name: str, **kwargs) -> str:
        """
        Start a new trace with a separate database session.
        Returns trace_id.
        """
        try:
            # Create new session for observability write
            # db = SessionLocal()
            # trace = Trace(name=trace_name, **kwargs)
            # db.add(trace)
            # db.commit()
            # trace_id = trace.id
            # db.close()
            # return trace_id
            
            # Mock implementation for prototype
            import uuid
            return str(uuid.uuid4())
            
        except Exception as e:
            logger.error(f"Failed to start trace {trace_name}: {e}")
            # Best-effort: if observability fails, don't affect main request
            return ""
    
    def end_trace(self, trace_id: str, status: str = "ok", **kwargs) -> bool:
        """
        End a trace with a separate database session.
        """
        try:
            # Create new session for observability write
            # db = SessionLocal()
            # trace = db.query(Trace).filter(Trace.id == trace_id).first()
            # if trace:
            #     trace.status = status
            #     trace.end_time = datetime.utcnow()
            #     db.commit()
            # db.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to end trace {trace_id}: {e}")
            return False
    
    def start_span(self, trace_id: str, span_name: str, **kwargs) -> str:
        """
        Start a new span with a separate database session.
        Returns span_id.
        """
        try:
            # Create new session for observability write
            # db = SessionLocal()
            # span = Span(trace_id=trace_id, name=span_name, **kwargs)
            # db.add(span)
            # db.commit()
            # span_id = span.id
            # db.close()
            # return span_id
            
            # Mock implementation for prototype
            import uuid
            return str(uuid.uuid4())
            
        except Exception as e:
            logger.error(f"Failed to start span {span_name} in trace {trace_id}: {e}")
            return ""
    
    def end_span(self, span_id: str, status: str = "ok", **kwargs) -> bool:
        """
        End a span with a separate database session.
        """
        try:
            # Create new session for observability write
            # db = SessionLocal()
            # span = db.query(Span).filter(Span.id == span_id).first()
            # if span:
            #     span.status = status
            #     span.end_time = datetime.utcnow()
            #     db.commit()
            # db.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to end span {span_id}: {e}")
            return False
    
    def add_event(self, trace_id: str, event_type: str, **kwargs) -> bool:
        """
        Add an event with a separate database session.
        """
        try:
            # Create new session for observability write
            # db = SessionLocal()
            # event = Event(trace_id=trace_id, type=event_type, **kwargs)
            # db.add(event)
            # db.commit()
            # db.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to add event {event_type} to trace {trace_id}: {e}")
            return False
    
    def record_metric(self, trace_id: str, metric_name: str, value: float, **kwargs) -> bool:
        """
        Record a metric with a separate database session.
        """
        try:
            # Create new session for observability write
            # db = SessionLocal()
            # metric = Metric(trace_id=trace_id, name=metric_name, value=value, **kwargs)
            # db.add(metric)
            # db.commit()
            # db.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to record metric {metric_name} for trace {trace_id}: {e}")
            return False
    
    def record_token_usage(self, trace_id: str, model: str, input_tokens: int, output_tokens: int, **kwargs) -> bool:
        """
        Record token usage with a separate database session.
        """
        try:
            # Create new session for observability write
            # db = SessionLocal()
            # token_usage = TokenUsage(
            #     trace_id=trace_id, 
            #     model=model, 
            #     input_tokens=input_tokens, 
            #     output_tokens=output_tokens, 
            #     **kwargs
            # )
            # db.add(token_usage)
            # db.commit()
            # db.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to record token usage for trace {trace_id}: {e}")
            return False
    
    def delete_old_traces(self, days_old: int = 30) -> int:
        """
        Delete old traces with a separate database session.
        Returns number of deleted traces.
        """
        try:
            # Create new session for observability write
            # db = SessionLocal()
            # count = db.query(Trace).filter(
            #     Trace.created_at < datetime.utcnow() - timedelta(days=days_old)
            # ).delete()
            # db.commit()
            # db.close()
            return 0
            
        except Exception as e:
            logger.error(f"Failed to delete old traces: {e}")
            return 0
    
    # Query methods - still accept db parameter for RBAC/token scoping
    
    def get_trace(self, db: Session, trace_id: str) -> Optional[Dict]:
        """
        Get a trace using the provided session (for RBAC scoping).
        """
        # In real implementation: return db.query(Trace).filter(Trace.id == trace_id).first()
        return {"id": trace_id, "name": "test_trace"}
    
    def get_traces(self, db: Session, **filters) -> list:
        """
        Get traces using the provided session (for RBAC scoping).
        """
        # In real implementation: return db.query(Trace).filter(**filters).all()
        return []
    
    def query_traces(self, db: Session, **query_params) -> list:
        """
        Query traces using the provided session (for RBAC scoping).
        """
        # In real implementation: implement query logic
        return []
    
    # Context managers - create and manage their own sessions
    
    @contextmanager
    def trace_span(self, trace_id: str, span_name: str, **kwargs) -> Generator[str, None, None]:
        """
        Context manager for tracing spans with separate session management.
        
        Yields span_id.
        """
        span_id = ""
        try:
            # Start span with separate session
            span_id = self.start_span(trace_id, span_name, **kwargs)
            yield span_id
        except Exception as e:
            logger.error(f"Error in trace_span context for {span_name}: {e}")
            raise
        finally:
            # Always try to end the span
            if span_id:
                self.end_span(span_id, status="error" if 'e' in locals() else "ok")
    
    @contextmanager
    def trace_tool_invocation(self, trace_id: str, tool_name: str, **kwargs) -> Generator[Tuple[Optional[str], Dict[str, Any]], None, None]:
        """
        Context manager for tracing tool invocations with separate session management.
        
        Yields (span_id, context_dict).
        """
        span_id = ""
        context = {"tool": tool_name, **kwargs}
        try:
            span_id = self.start_span(trace_id, f"tool.{tool_name}", **kwargs)
            yield (span_id, context)
        except Exception as e:
            logger.error(f"Error in trace_tool_invocation context for {tool_name}: {e}")
            raise
        finally:
            if span_id:
                self.end_span(span_id, status="error" if 'e' in locals() else "ok")
    
    @contextmanager
    def trace_a2a_request(self, trace_id: str, target_agent: str, **kwargs) -> Generator[Tuple[Optional[str], Dict[str, Any]], None, None]:
        """
        Context manager for tracing A2A requests with separate session management.
        
        Yields (span_id, context_dict).
        """
        span_id = ""
        context = {"target_agent": target_agent, **kwargs}
        try:
            span_id = self.start_span(trace_id, f"a2a.{target_agent}", **kwargs)
            yield (span_id, context)
        except Exception as e:
            logger.error(f"Error in trace_a2a_request context for {target_agent}: {e}")
            raise
        finally:
            if span_id:
                self.end_span(span_id, status="error" if 'e' in locals() else "ok")

# Global service instance
service = ObservabilityService()

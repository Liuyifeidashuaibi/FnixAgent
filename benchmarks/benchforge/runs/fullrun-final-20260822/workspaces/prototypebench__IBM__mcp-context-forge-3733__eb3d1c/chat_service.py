import asyncio
import logging
from typing import AsyncGenerator, Dict, Any

logger = logging.getLogger(__name__)


def chat_events() -> AsyncGenerator[Dict[str, Any], None]:
    """
    Generator that yields chat events during streaming.
    Handles different error types appropriately:
    - ConnectionError and TimeoutError: propagate as-is for router to handle
    - Other errors (tool failures, parsing errors, model issues): wrap in RuntimeError with recoverable=True
    """
    try:
        # Simulate chat event streaming logic
        # This would normally contain the actual chat processing code
        
        # Example: yield chat events
        yield {"type": "message", "content": "Hello, how can I help you?"}
        
        # Simulate some processing that might fail
        # ... chat processing logic ...
        
    except (ConnectionError, TimeoutError) as e:
        # Let ConnectionError and TimeoutError propagate with original type
        # so router's existing handlers can catch them correctly
        logger.warning(f"Connection/timeout error during chat streaming: {e}")
        raise
    
    except Exception as e:
        # For all other exceptions (tool failures, parsing errors, model issues),
        # wrap in RuntimeError but mark as recoverable=True
        # since the session is still valid
        error_msg = f"Chat processing error: {str(e)}"
        logger.error(error_msg)
        
        # Create a RuntimeError that indicates it's recoverable
        # In a real implementation, this might be a custom exception
        # or include metadata about recoverability
        raise RuntimeError(error_msg)

# Alternative implementation with explicit recoverable flag support
# if the router expects structured error information
class ChatRuntimeError(RuntimeError):
    """RuntimeError specifically for chat processing with recoverable flag"""
    
    def __init__(self, message: str, recoverable: bool = True):
        super().__init__(message)
        self.recoverable = recoverable


def chat_events_v2() -> AsyncGenerator[Dict[str, Any], None]:
    """
    Enhanced version with explicit recoverable flag support.
    """
    try:
        # Simulate chat event streaming logic
        yield {"type": "message", "content": "Hello, how can I help you?"}
        
        # ... chat processing logic ...
        
    except (ConnectionError, TimeoutError) as e:
        logger.warning(f"Connection/timeout error during chat streaming: {e}")
        raise
    
    except Exception as e:
        error_msg = f"Chat processing error: {str(e)}"
        logger.error(error_msg)
        
        # Wrap in ChatRuntimeError with recoverable=True
        raise ChatRuntimeError(error_msg, recoverable=True)

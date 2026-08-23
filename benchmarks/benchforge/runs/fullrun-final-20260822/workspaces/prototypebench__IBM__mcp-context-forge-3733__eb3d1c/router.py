import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ChatRouter:
    """
    Router that handles chat events and errors.
    Contains existing handlers for ConnectionError and TimeoutError.
    """
    
    def __init__(self):
        pass
    
    def handle_chat_event(self, event: Dict[str, Any]) -> None:
        """Handle individual chat events"""
        # Process the event
        pass
    
    def handle_error(self, error: Exception) -> Dict[str, Any]:
        """
        Handle errors from chat_events() generator.
        Returns response with recoverable flag.
        """
        result = {
            "error": str(error),
            "recoverable": False  # default
        }
        
        # Existing handlers for ConnectionError and TimeoutError
        if isinstance(error, (ConnectionError, TimeoutError)):
            logger.warning(f"Handling connection/timeout error: {error}")
            result["recoverable"] = False
            result["message"] = "Connection lost. Attempting to reconnect..."
            return result
        
        # Handle RuntimeError from chat_events()
        # In the fixed version, these should be recoverable
        elif isinstance(error, RuntimeError):
            # Check if it's a ChatRuntimeError with recoverable flag
            if hasattr(error, 'recoverable'):
                result["recoverable"] = error.recoverable
            else:
                # For standard RuntimeError, assume recoverable in new implementation
                result["recoverable"] = True
            
            result["message"] = "An error occurred during chat processing."
            return result
        
        # Other unexpected errors
        else:
            logger.error(f"Unexpected error type: {type(error)} - {error}")
            result["recoverable"] = False
            result["message"] = "Unexpected error occurred."
            return result
        
        return result

# Global router instance
chat_router = ChatRouter()

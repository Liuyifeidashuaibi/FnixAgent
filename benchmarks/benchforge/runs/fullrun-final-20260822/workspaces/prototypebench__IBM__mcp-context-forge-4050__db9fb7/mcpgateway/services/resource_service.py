from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

# Assuming these imports will be available in the actual environment
# from mcpgateway.services.observability_service import service


class ResourceService:
    """
    Service for handling resource-related operations.
    
    Uses the new observability service API where write methods
    do not require a db parameter and create their own sessions.
    """
    
    def __init__(self):
        pass
    
    def get_resource(self, resource_id: str, **kwargs) -> Dict[str, Any]:
        """
        Get a resource with observability tracing.
        """
        try:
            trace_id = service.start_trace("resource.get", resource_id=resource_id)
            
            with service.trace_span(trace_id, "resource.fetch") as span_id:
                # Simulate resource fetching
                resource = {
                    "id": resource_id,
                    "type": "document",
                    "content": "Sample content"
                }
                
                # Record metrics
                service.record_metric(trace_id, "resource.size", len(str(resource)))
                
                return resource
                
        except Exception as e:
            logger.error(f"Error getting resource {resource_id}: {e}")
            raise
        
        finally:
            if 'trace_id' in locals():
                service.end_trace(trace_id, status="error" if 'e' in locals() else "ok")
    
    def create_resource(self, resource_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Create a resource with observability tracing.
        """
        try:
            trace_id = service.start_trace("resource.create", 
                                         resource_type=resource_data.get('type'))
            
            with service.trace_span(trace_id, "resource.create") as span_id:
                # Simulate resource creation
                created_resource = {
                    "id": f"res_{hash(str(resource_data)) % 1000000}",
                    **resource_data
                }
                
                # Record token usage if applicable
                if 'content' in resource_data:
                    service.record_token_usage(trace_id, "resource", 
                                             len(str(resource_data)), 
                                             len(str(created_resource)))
                
                return created_resource
                
        except Exception as e:
            logger.error(f"Error creating resource: {e}")
            raise
        
        finally:
            if 'trace_id' in locals():
                service.end_trace(trace_id, status="error" if 'e' in locals() else "ok")

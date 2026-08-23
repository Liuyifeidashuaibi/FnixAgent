from sqlalchemy.orm import Session
from typing import List, Optional

from mcpgateway.db import Resource

def get_resources_for_server(db: Session, server_id: int, include_metrics: bool = False) -> List[dict]:
    """
    Get resources for a server, optionally including metrics summary.
    
    Args:
        db: Database session
        server_id: ID of the server
        include_metrics: Whether to include metrics summary in response
    
    Returns:
        List of resource dictionaries
    """
    # Query resources for the server
    resources = db.query(Resource).filter(Resource.server_id == server_id).all()
    
    result = []
    for resource in resources:
        resource_dict = {
            'id': resource.id,
            'name': resource.name,
            'type': resource.type,
            'created_at': resource.created_at.isoformat() if resource.created_at else None,
            'updated_at': resource.updated_at.isoformat() if resource.updated_at else None,
        }
        
        # Include metrics if requested
        if include_metrics:
            try:
                metrics_summary = resource.metrics_summary
                resource_dict['metrics'] = metrics_summary
            except Exception as e:
                # Handle cases where metrics might not be available
                resource_dict['metrics'] = {
                    'total_executions': 0,
                    'successful_executions': 0,
                    'failed_executions': 0,
                    'failure_rate': 0.0,
                    'avg_response_time': 0.0,
                    'last_execution_time': None
                }
        
        result.append(resource_dict)
    
    return result

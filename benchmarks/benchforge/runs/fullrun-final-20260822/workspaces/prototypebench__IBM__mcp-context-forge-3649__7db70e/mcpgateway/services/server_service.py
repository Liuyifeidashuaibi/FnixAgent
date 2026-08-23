from sqlalchemy.orm import Session
from typing import List, Optional

from mcpgateway.db import Server

def get_servers(db: Session, include_metrics: bool = False) -> List[dict]:
    """
    Get all servers, optionally including metrics summary.
    
    Args:
        db: Database session
        include_metrics: Whether to include metrics summary in response
    
    Returns:
        List of server dictionaries
    """
    # Query all servers
    servers = db.query(Server).all()
    
    result = []
    for server in servers:
        server_dict = {
            'id': server.id,
            'name': server.name,
            'status': server.status,
            'created_at': server.created_at.isoformat() if server.created_at else None,
            'updated_at': server.updated_at.isoformat() if server.updated_at else None,
        }
        
        # Include metrics if requested
        if include_metrics:
            try:
                metrics_summary = server.metrics_summary
                server_dict['metrics'] = metrics_summary
            except Exception as e:
                # Handle cases where metrics might not be available
                server_dict['metrics'] = {
                    'total_executions': 0,
                    'successful_executions': 0,
                    'failed_executions': 0,
                    'failure_rate': 0.0,
                    'avg_response_time': 0.0,
                    'last_execution_time': None
                }
        
        result.append(server_dict)
    
    return result

from sqlalchemy.orm import Session
from typing import List, Optional

from mcpgateway.db import Tool

def get_tools_for_server(db: Session, server_id: int, include_metrics: bool = False) -> List[dict]:
    """
    Get tools for a server, optionally including metrics summary.
    
    Args:
        db: Database session
        server_id: ID of the server
        include_metrics: Whether to include metrics summary in response
    
    Returns:
        List of tool dictionaries
    """
    # Query tools for the server
    tools = db.query(Tool).filter(Tool.server_id == server_id).all()
    
    result = []
    for tool in tools:
        tool_dict = {
            'id': tool.id,
            'name': tool.name,
            'description': tool.description,
            'created_at': tool.created_at.isoformat() if tool.created_at else None,
            'updated_at': tool.updated_at.isoformat() if tool.updated_at else None,
        }
        
        # Include metrics if requested
        if include_metrics:
            try:
                metrics_summary = tool.metrics_summary
                tool_dict['metrics'] = metrics_summary
            except Exception as e:
                # Handle cases where metrics might not be available
                tool_dict['metrics'] = {
                    'total_executions': 0,
                    'successful_executions': 0,
                    'failed_executions': 0,
                    'failure_rate': 0.0,
                    'avg_response_time': 0.0,
                    'last_execution_time': None
                }
        
        result.append(tool_dict)
    
    return result

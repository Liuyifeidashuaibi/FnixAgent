from sqlalchemy.orm import Session
from typing import List, Optional

from mcpgateway.db import Prompt

def get_prompts_for_server(db: Session, server_id: int, include_metrics: bool = False) -> List[dict]:
    """
    Get prompts for a server, optionally including metrics summary.
    
    Args:
        db: Database session
        server_id: ID of the server
        include_metrics: Whether to include metrics summary in response
    
    Returns:
        List of prompt dictionaries
    """
    # Query prompts for the server
    prompts = db.query(Prompt).filter(Prompt.server_id == server_id).all()
    
    result = []
    for prompt in prompts:
        prompt_dict = {
            'id': prompt.id,
            'name': prompt.name,
            'content': prompt.content,
            'created_at': prompt.created_at.isoformat() if prompt.created_at else None,
            'updated_at': prompt.updated_at.isoformat() if prompt.updated_at else None,
        }
        
        # Include metrics if requested
        if include_metrics:
            try:
                metrics_summary = prompt.metrics_summary
                prompt_dict['metrics'] = metrics_summary
            except Exception as e:
                # Handle cases where metrics might not be available
                prompt_dict['metrics'] = {
                    'total_executions': 0,
                    'successful_executions': 0,
                    'failed_executions': 0,
                    'failure_rate': 0.0,
                    'avg_response_time': 0.0,
                    'last_execution_time': None
                }
        
        result.append(prompt_dict)
    
    return result

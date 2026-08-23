from typing import Dict, Any, Optional

# Mock imports for the actual implementation
from mcpgateway.services.a2a_service import get_agent, invoke_agent


def admin_test_a2a_agent(
    agent_id: str,
    user_dict: Dict[str, Any],
    db: Any  # database connection
) -> Dict[str, Any]:
    """
    Test an A2A agent as an admin user.
    
    Extracts is_admin and token_teams from the authenticated user dict
    and forwards them to both get_agent and invoke_agent.
    """
    is_admin = user_dict.get('is_admin', False)
    token_teams = user_dict.get('teams')
    
    # For admin bypass, set invoke_user_email to None to preserve semantics
    invoke_user_email = None if is_admin else user_dict.get('email')
    
    # Get the agent with proper context
    agent = get_agent(db, agent_id, user_email=invoke_user_email, token_teams=token_teams)
    
    # Invoke the agent with proper context
    result = invoke_agent(
        db=db,
        agent_id=agent_id,
        user_email=invoke_user_email,
        token_teams=token_teams
    )
    
    return result

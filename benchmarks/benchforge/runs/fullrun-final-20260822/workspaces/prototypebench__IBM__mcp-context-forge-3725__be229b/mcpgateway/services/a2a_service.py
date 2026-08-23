from typing import Optional, List

# Mock imports for the actual implementation
class Agent:
    def __init__(self, team_id: str, visibility: str):
        self.team_id = team_id
        self.visibility = visibility


def _check_agent_access(
    agent: Agent,
    token_teams: Optional[List[str]]
) -> bool:
    """
    Check if the user has access to the agent based on visibility and teams.
    
    Added guard for token_teams=None (admin bypass case).
    """
    if agent.visibility == "public":
        return True
    
    if agent.visibility == "team":
        # Admin bypass - full access when token_teams is None
        if token_teams is None:
            return True
        return agent.team_id in token_teams
    
    # Default deny for unknown visibility types
    return False


def get_agent(db, agent_id: str, user_email: Optional[str] = None, token_teams: Optional[List[str]] = None) -> Agent:
    # Mock implementation
    pass


def invoke_agent(db, agent_id: str, user_email: Optional[str] = None, token_teams: Optional[List[str]] = None) -> dict:
    # Mock implementation
    pass

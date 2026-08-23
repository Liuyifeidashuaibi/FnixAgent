from typing import List, Dict, Optional


def get_team_permissions(token_scopes: List[str], team_id: Optional[str] = None) -> List[Dict]:
    """
    Get permissions for a team, preserving global and personal roles
    even when team_id is out of token scope.
    
    Args:
        token_scopes: List of scopes granted to the token
        team_id: The team ID to check permissions for
    
    Returns:
        List of permission objects including global and personal roles
    """
    permissions = []
    
    # Always include global roles (admin, viewer, etc.)
    # These are not tied to specific teams
    global_roles = [
        {"role": "admin", "scope": "global"},
        {"role": "viewer", "scope": "global"},
        {"role": "editor", "scope": "global"}
    ]
    permissions.extend(global_roles)
    
    # Always include personal roles (user-specific permissions)
    personal_roles = [
        {"role": "owner", "scope": "personal"},
        {"role": "member", "scope": "personal"}
    ]
    permissions.extend(personal_roles)
    
    # Only add team-specific roles if team_id is in token scope
    if team_id and f"team:{team_id}" in token_scopes:
        # Add team-specific roles
        team_roles = [
            {"role": "admin", "scope": "team", "team_id": team_id},
            {"role": "member", "scope": "team", "team_id": team_id},
            {"role": "viewer", "scope": "team", "team_id": team_id}
        ]
        permissions.extend(team_roles)
    
    return permissions


def has_team_permission(token_scopes: List[str], team_id: Optional[str] = None, 
                        required_role: str = "member") -> bool:
    """
    Check if token has required permission for team.
    Preserves global and personal roles for join operations.
    """
    permissions = get_team_permissions(token_scopes, team_id)
    
    # Check for required role in any scope (global, personal, or team)
    for perm in permissions:
        if perm.get("role") == required_role:
            return True
    
    return False

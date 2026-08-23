from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass


class PermissionService:
    """
    Service for managing and checking permissions in the MCP Context Forge system.
    Implements two-layer RBAC model:
    - Layer 1: Session-token team narrowing (visibility)
    - Layer 2: Permission checks (RBAC)
    """

    def __init__(self):
        self._cache = {}

    def get_user_permissions(
        self,
        user_id: str,
        include_all_teams: bool = False,
        token_teams: Optional[List[str]] = None
    ) -> Set[str]:
        """
        Get all permissions for a user.
        
        Args:
            user_id: The user identifier
            include_all_teams: Whether to include permissions from all teams the user belongs to
            token_teams: List of teams from session token for Layer 1 narrowing
        
        Returns:
            Set of permission strings
        """
        # Generate cache key that includes token_teams for proper isolation
        cache_key_parts = [user_id, str(include_all_teams)]
        if token_teams is not None:
            # Sort token_teams for consistent cache keys
            sorted_teams = sorted(token_teams)
            cache_key_parts.append(','.join(sorted_teams))
        else:
            cache_key_parts.append('None')
        
        cache_key = '|'.join(cache_key_parts)
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Get user roles with token_teams filtering
        roles = self._get_user_roles(
            user_id=user_id,
            include_all_teams=include_all_teams,
            token_teams=token_teams
        )
        
        # Aggregate permissions from roles
        permissions = set()
        for role in roles:
            # Mock permission aggregation logic
            if hasattr(role, 'permissions'):
                permissions.update(role.permissions)
        
        self._cache[cache_key] = permissions
        return permissions

    def _get_user_roles(
        self,
        user_id: str,
        include_all_teams: bool = False,
        token_teams: Optional[List[str]] = None
    ) -> List[Any]:
        """
        Get roles for a user, with optional token_teams filtering.
        
        Args:
            user_id: The user identifier
            include_all_teams: Whether to include roles from all teams
            token_teams: List of teams from session token for narrowing
        
        Returns:
            List of role objects
        """
        # Mock role retrieval logic
        roles = []
        
        # When include_all_teams=True and token_teams is non-empty, filter by token_teams
        if include_all_teams and token_teams is not None and len(token_teams) > 0:
            # Filter to only include roles from specified token_teams
            # This enforces Layer 1 narrowing in Layer 2 permission checks
            for team_id in token_teams:
                # Add mock roles for each token team
                roles.append(self._get_team_roles(user_id, team_id))
        elif include_all_teams:
            # Include roles from all teams the user belongs to
            roles = self._get_all_teams_roles(user_id)
        else:
            # Default behavior - no team-specific roles
            pass
        
        return roles

    def _get_team_roles(self, user_id: str, team_id: str) -> Any:
        """Get roles for a specific team."""
        # Mock implementation
        return type('Role', (), {'team_id': team_id, 'permissions': []})()

    def _get_all_teams_roles(self, user_id: str) -> List[Any]:
        """Get roles from all teams the user belongs to."""
        # Mock implementation
        return []

    def check_permission(
        self,
        user_id: str,
        permission: str,
        team_id: Optional[str] = None,
        token_teams: Optional[List[str]] = None
    ) -> bool:
        """
        Check if a user has a specific permission.
        
        Args:
            user_id: The user identifier
            permission: The permission to check
            team_id: Optional team ID to scope the check
            token_teams: List of teams from session token for Layer 1 narrowing
        
        Returns:
            Boolean indicating if permission is granted
        """
        # Get user permissions with token_teams narrowing
        user_permissions = self.get_user_permissions(
            user_id=user_id,
            include_all_teams=True,
            token_teams=token_teams
        )
        
        return permission in user_permissions

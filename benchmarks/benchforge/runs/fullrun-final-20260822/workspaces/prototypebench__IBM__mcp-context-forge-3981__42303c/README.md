# Team Permissions Fix

## Bug Description
The team permission check was returning `[]` when `team_id` was out of token scope, incorrectly discarding global and personal roles needed for the join endpoint.

## Fix Summary
Changed the guard logic to:
- Always include global roles (admin, viewer, editor)
- Always include personal roles (owner, member)
- Only add team-specific roles when the team_id is explicitly in the token scopes

This ensures that join operations can still proceed using global or personal permissions even when the specific team is not in the token's scope.

## Files Modified
- `team_permissions.py`: Fixed permission logic
- `test_team_permissions.py`: Added tests to verify the fix

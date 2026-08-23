from fastapi import HTTPException, status
from typing import Optional

# Function to require an authenticated session
async def _require_authenticated_session(auth_method: str):
    if auth_method == "api_token":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Token management requires an interactive session (JWT from web login or SSO). "
                "API tokens cannot create, list, or revoke other tokens."
            ),
        )

# Function to create a token with proper team inheritance
async def create_token(current_user: dict, team_id: Optional[int] = None):
    # Get the user's teams from the token_teams key
    user_teams = current_user.get("token_teams", [])

    # If no team_id is provided, use the first team the user belongs to
    effective_team_id = team_id or (user_teams[0] if user_teams else None)

    # Admin users can create globally scoped tokens (team_id=None)
    if current_user.get("is_admin"):  # Assuming there's an is_admin flag
        effective_team_id = None

    # Create the token with the effective team ID
    # (Token creation logic here)
    return {
        "token": "generated_token",
        "team_id": effective_team_id,
    }

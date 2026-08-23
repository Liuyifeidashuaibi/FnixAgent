from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from mcpgateway.database import get_db

router = APIRouter()

# Feature flag - would be loaded from config in real implementation
ALLOW_TEAM_JOIN_REQUESTS = True


def get_feature_flag(flag_name: str) -> bool:
    """
    Get feature flag value.
    In real implementation, this would read from config or database.
    """
    if flag_name == "allow_team_join_requests":
        return ALLOW_TEAM_JOIN_REQUESTS
    return False


@router.get("/admin/feature-flags")
def get_feature_flags():
    """
    Get current feature flags.
    """
    return {
        "allow_team_join_requests": get_feature_flag("allow_team_join_requests")
    }


@router.post("/admin/feature-flags/{flag_name}/toggle")
def toggle_feature_flag(flag_name: str, enabled: bool):
    """
    Toggle a feature flag.
    In real implementation, this would update the config/database.
    """
    global ALLOW_TEAM_JOIN_REQUESTS
    
    if flag_name == "allow_team_join_requests":
        ALLOW_TEAM_JOIN_REQUESTS = enabled
        return {
            "status": "success",
            "message": f"Feature flag '{flag_name}' updated to {enabled}"
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown feature flag: {flag_name}"
        )

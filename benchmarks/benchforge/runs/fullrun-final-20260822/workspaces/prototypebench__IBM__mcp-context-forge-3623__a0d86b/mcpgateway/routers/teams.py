from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional

from mcpgateway.services.team_management_service import TeamManagementService
from mcpgateway.database import get_db

router = APIRouter()


def get_team_management_service(db: Session = Depends(get_db)):
    return TeamManagementService(db)


@router.post("/teams/{team_id}/join-requests")
def request_to_join_team(
    team_id: int,
    user_id: int,
    max_teams: int = 5,
    service: TeamManagementService = Depends(get_team_management_service),
):
    """
    Request to join a team.
    Returns 400 Bad Request for validation errors instead of 500.
    """
    try:
        result = service.create_join_request(user_id, team_id, max_teams)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        # Re-raise other exceptions as 500
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@router.post("/join-requests/{request_id}/approve")
def approve_join_request(
    request_id: int,
    service: TeamManagementService = Depends(get_team_management_service),
):
    """
    Approve a join request.
    Returns 400 Bad Request for validation errors instead of 500.
    """
    try:
        result = service.approve_join_request(request_id)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        # Re-raise other exceptions as 500
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

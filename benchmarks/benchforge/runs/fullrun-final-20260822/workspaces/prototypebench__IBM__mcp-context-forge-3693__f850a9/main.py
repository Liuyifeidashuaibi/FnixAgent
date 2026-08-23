from fastapi import FastAPI, Query, Depends, HTTPException
from typing import List, Optional
import jwt
from pydantic import BaseModel

app = FastAPI(title="MCP Context Forge Tools API")

# Mock database storage
TOOLS_DB = []

# Pydantic models
class ToolBase(BaseModel):
    name: str
    description: str
    visibility: str  # 'public', 'team', 'private'
    teamId: Optional[str] = None

class ToolCreate(ToolBase):
    pass

class Tool(ToolBase):
    id: int

# Mock authentication functions
def get_current_user(token: str = Depends(lambda: "mock_token")) -> dict:
    """Mock authentication - in real app this would decode JWT"""
    try:
        # Decode token to get user info
        payload = jwt.decode(token, "secret_key", algorithms=["HS256"])
        return {
            "user_id": payload.get("user_id"),
            "is_admin": payload.get("is_admin", False),
            "team_id": payload.get("team_id")
        }
    except Exception:
        # Invalid token - return basic user
        return {"user_id": "anonymous", "is_admin": False, "team_id": None}

# Helper function to filter tools by visibility
def filter_tools_by_visibility(tools: List[Tool], visibility: str, current_user: dict) -> List[Tool]:
    """
    Filter tools by visibility parameter.
    Admin tokens should respect the explicit visibility filter,
    not bypass it entirely.
    """
    if visibility == "public":
        return [tool for tool in tools if tool.visibility == "public"]
    elif visibility == "team":
        if current_user.get("is_admin", False):
            # Admin can see all team tools, but still filter by team visibility
            return [tool for tool in tools if tool.visibility == "team"]
        else:
            # Regular user sees only their team's tools
            team_id = current_user.get("team_id")
            if not team_id:
                return []
            return [tool for tool in tools if tool.visibility == "team" and tool.teamId == team_id]
    elif visibility == "private":
        if current_user.get("is_admin", False):
            # Admin can see all private tools
            return [tool for tool in tools if tool.visibility == "private"]
        else:
            # Regular user sees only their own private tools
            user_id = current_user.get("user_id")
            if not user_id:
                return []
            return [tool for tool in tools if tool.visibility == "private" and 
                   hasattr(tool, 'created_by') and tool.created_by == user_id]
    return tools

@app.get("/tools")
def list_tools(
    visibility: Optional[str] = Query(None, description="Filter by visibility: public, team, or private"),
    limit: Optional[int] = Query(100, description="Maximum number of results"),
    offset: Optional[int] = Query(0, description="Offset for pagination"),
    current_user: dict = Depends(get_current_user)
):
    """
    List tools with visibility filtering.
    
    The visibility filter is always applied when specified,
    even for admin users. Admin bypass affects access control,
    not the filtering logic.
    """
    # Get all tools (in real app this would be from DB)
    tools = TOOLS_DB.copy()
    
    # Apply visibility filter if specified
    if visibility and visibility in ["public", "team", "private"]:
        tools = filter_tools_by_visibility(tools, visibility, current_user)
    
    # Apply pagination
    if limit > 0:
        tools = tools[offset:offset + limit]
    
    return tools

@app.post("/tools")
def create_tool(
    tool_data: ToolCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new tool.
    """
    # In real app, this would save to database
    # For demo, just add to mock DB
    new_tool = Tool(
        id=len(TOOLS_DB) + 1,
        name=tool_data.name,
        description=tool_data.description,
        visibility=tool_data.visibility,
        teamId=tool_data.teamId
    )
    TOOLS_DB.append(new_tool)
    return new_tool

# Add some sample data for testing
if __name__ == "__main__":
    import uvicorn
    
    # Add some sample tools for demonstration
    sample_tools = [
        Tool(id=1, name="public-tool-1", description="Public test tool 1", visibility="public"),
        Tool(id=2, name="public-tool-2", description="Public test tool 2", visibility="public"),
        Tool(id=3, name="team-tool-1", description="Team test tool 1", visibility="team", teamId="team-1"),
        Tool(id=4, name="team-tool-2", description="Team test tool 2", visibility="team", teamId="team-1"),
        Tool(id=5, name="private-tool-1", description="Private test tool 1", visibility="private"),
        Tool(id=6, name="private-tool-2", description="Private test tool 2", visibility="private"),
    ]
    
    TOOLS_DB.extend(sample_tools)
    
    uvicorn.run(app, host="0.0.0.0", port=4444)

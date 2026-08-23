from fastapi import FastAPI, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from mcpgateway.db import get_db
from mcpgateway.services.tool_service import get_tools_for_server
from mcpgateway.services.resource_service import get_resources_for_server
from mcpgateway.services.prompt_service import get_prompts_for_server
from mcpgateway.services.server_service import get_servers

app = FastAPI()

# Existing endpoint for tools with include_metrics support
@app.get("/servers/{server_id}/tools")
def get_server_tools(
    server_id: int,
    include_metrics: bool = Query(False, alias="include_metrics"),
    db: Session = Depends(get_db)
):
    return get_tools_for_server(db, server_id, include_metrics=include_metrics)

# New endpoint for resources with include_metrics support
@app.get("/servers/{server_id}/resources")
def get_server_resources(
    server_id: int,
    include_metrics: bool = Query(False, alias="include_metrics"),
    db: Session = Depends(get_db)
):
    return get_resources_for_server(db, server_id, include_metrics=include_metrics)

# New endpoint for prompts with include_metrics support
@app.get("/servers/{server_id}/prompts")
def get_server_prompts(
    server_id: int,
    include_metrics: bool = Query(False, alias="include_metrics"),
    db: Session = Depends(get_db)
):
    return get_prompts_for_server(db, server_id, include_metrics=include_metrics)

# New endpoint for servers with include_metrics support
@app.get("/servers")
def get_all_servers(
    include_metrics: bool = Query(False, alias="include_metrics"),
    db: Session = Depends(get_db)
):
    return get_servers(db, include_metrics=include_metrics)

# Additional endpoints would be here...

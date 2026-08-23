from typing import Optional, Literal
from pydantic import BaseModel


# Visibility enum values
class VisibilityEnum:
    PRIVATE = "private"
    PUBLIC = "public"
    ORG = "org"


# Base visibility type
VisibilityType = Literal["private", "public", "org"]


class GatewayUpdate(BaseModel):
    visibility: Optional[VisibilityType] = None


class ServerCreate(BaseModel):
    visibility: VisibilityType


class A2AAgentCreate(BaseModel):
    visibility: VisibilityType


class A2AAgentUpdate(BaseModel):
    visibility: Optional[VisibilityType] = None


class TeamResponse(BaseModel):
    visibility: Literal["private", "public"]


class TeamCreate(BaseModel):
    visibility: Literal["private", "public"]


class TeamUpdate(BaseModel):
    visibility: Optional[Literal["private", "public"]] = None

# These validators were removed as part of the PR
# They became dead code after migrating to Literal enums

from pydantic import validator


class ServerCreate:
    # This validator was removed
    # @validator("visibility")
    # def validate_visibility(cls, v):
    #     if v not in ["private", "public", "org"]:
    #         raise ValueError(f"Invalid visibility value: {v}")
    #     return v
    pass


class A2AAgentCreate:
    # This validator was removed
    # @validator("visibility")
    # def validate_visibility(cls, v):
    #     if v not in ["private", "public", "org"]:
    #         raise ValueError(f"Invalid visibility value: {v}")
    #     return v
    pass


class A2AAgentUpdate:
    # This validator was removed
    # @validator("visibility")
    # def validate_visibility(cls, v):
    #     if v and v not in ["private", "public", "org"]:
    #         raise ValueError(f"Invalid visibility value: {v}")
    #     return v
    pass

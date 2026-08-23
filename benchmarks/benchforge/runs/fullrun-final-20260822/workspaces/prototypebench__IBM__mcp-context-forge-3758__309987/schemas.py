from typing import Optional
from pydantic import BaseModel, Field


class GatewayCreate(BaseModel):
    """Schema for creating a new gateway."""
    # ... other fields ...
    client_cert: Optional[str] = Field(None, description="Client TLS certificate for mTLS")
    client_key: Optional[str] = Field(None, description="Client TLS key for mTLS")


class GatewayUpdate(BaseModel):
    """Schema for updating an existing gateway."""
    # ... other fields ...
    client_cert: Optional[str] = Field(None, description="Client TLS certificate for mTLS")
    client_key: Optional[str] = Field(None, description="Client TLS key for mTLS")


class GatewayRead(BaseModel):
    """Schema for reading gateway information."""
    # ... other fields ...
    client_cert: Optional[str] = Field(default=None, description="Client TLS certificate for mTLS")
    client_key: Optional[str] = Field(default=None, description="Client TLS key for mTLS")

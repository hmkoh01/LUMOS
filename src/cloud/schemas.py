from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class DevLoginRequest(BaseModel):
    email: str
    name: Optional[str] = "Demo User"
    plan: str = "free"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]


class RefreshRequest(BaseModel):
    refresh_token: str


class DeviceRegisterRequest(BaseModel):
    device_name: str
    os: str
    app_version: str = "0.1.0"
    device_fingerprint_hash: str = "placeholder_hash"


class UsageEventRequest(BaseModel):
    event_type: str
    quantity: int = Field(default=1, ge=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)

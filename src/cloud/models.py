from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CloudUser:
    id: str
    email: str
    name: Optional[str]
    plan: str
    status: str


@dataclass(frozen=True)
class CloudSession:
    id: str
    user_id: str
    device_id: Optional[str]
    expires_at: str
    revoked_at: Optional[str] = None


@dataclass(frozen=True)
class CloudDevice:
    id: str
    user_id: str
    device_name: str
    os: str
    app_version: str
    device_fingerprint_hash: str
    status: str


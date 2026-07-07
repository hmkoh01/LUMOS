from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class UserAccount:
    """Future cloud account identity.

    TODO: connect this to real signup/login in a later phase.
    """

    id: str
    email: str
    name: Optional[str] = None
    status: str = "active"
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


@dataclass(frozen=True)
class AuthUser:
    """User identity visible to the local app auth state."""

    id: str
    email: str
    name: Optional[str] = None
    plan: str = "free"
    status: str = "active"

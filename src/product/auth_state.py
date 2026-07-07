from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from src.product.account import AuthUser
from src.product.entitlements import PlanEntitlement


class AuthStatus(str, Enum):
    ANONYMOUS = "anonymous"
    SIGNED_IN = "signed_in"
    EXPIRED = "expired"
    OFFLINE_GRACE = "offline_grace"
    ERROR = "error"


@dataclass(frozen=True)
class AuthSession:
    """Local representation of an auth session.

    Mock sessions must use tokens prefixed with `mock_`.
    """

    user_id: str
    device_id: str
    access_token: str
    refresh_token: str
    expires_at: datetime
    is_mock: bool = True

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        return (now or datetime.utcnow()) >= self.expires_at


@dataclass(frozen=True)
class AuthState:
    status: AuthStatus = AuthStatus.ANONYMOUS
    user: Optional[AuthUser] = None
    session: Optional[AuthSession] = None
    entitlement_summary: Dict[str, PlanEntitlement] = field(default_factory=dict)
    last_checked_at: Optional[datetime] = None
    error_code: Optional[str] = None

    @property
    def is_signed_in(self) -> bool:
        return self.status == AuthStatus.SIGNED_IN and self.user is not None and self.session is not None

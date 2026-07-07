from datetime import datetime, timedelta
from typing import List, Optional

from src.product.account import AuthUser
from src.product.auth_state import AuthSession, AuthState, AuthStatus
from src.product.device import MockDeviceRegistry, RegisteredDevice, build_local_device_info
from src.product.entitlements import MockEntitlementService, PlanEntitlement


class MockAuthService:
    """Network-free auth boundary for future local/cloud integration tests."""

    def __init__(self, plan: str = "free", session_minutes: int = 60):
        self.plan = plan if plan in {"free", "pro", "team"} else "free"
        self.session_minutes = max(1, int(session_minutes))
        self.device_registry = MockDeviceRegistry()
        self.entitlements = MockEntitlementService(self.plan)
        self.usage_events: List[dict] = []
        self._state = AuthState()

    def login(self, email: str = "demo@lumos.local", name: str = "Demo User", device_name: Optional[str] = None) -> AuthState:
        user = AuthUser(id=self._mock_user_id(email), email=email, name=name, plan=self.plan)
        device = self.register_device(user.id, device_name=device_name)
        session = self._new_session(user.id, device.id)
        self._state = AuthState(
            status=AuthStatus.SIGNED_IN,
            user=user,
            session=session,
            entitlement_summary=self.entitlements.get_entitlements(user.id, device.id),
            last_checked_at=datetime.utcnow(),
        )
        return self._state

    def logout(self) -> AuthState:
        self._state = AuthState(status=AuthStatus.ANONYMOUS, last_checked_at=datetime.utcnow())
        return self._state

    def refresh(self) -> AuthState:
        if not self._state.user or not self._state.session:
            self._state = AuthState(status=AuthStatus.ERROR, error_code="AUTH_REQUIRED", last_checked_at=datetime.utcnow())
            return self._state
        session = self._new_session(self._state.user.id, self._state.session.device_id)
        self._state = AuthState(
            status=AuthStatus.SIGNED_IN,
            user=self._state.user,
            session=session,
            entitlement_summary=self.entitlements.get_entitlements(self._state.user.id, session.device_id),
            last_checked_at=datetime.utcnow(),
        )
        return self._state

    def current_state(self) -> AuthState:
        if self._state.session and self._state.session.is_expired():
            return AuthState(
                status=AuthStatus.EXPIRED,
                user=self._state.user,
                session=self._state.session,
                entitlement_summary=self._state.entitlement_summary,
                last_checked_at=datetime.utcnow(),
                error_code="TOKEN_EXPIRED",
            )
        return self._state

    def register_device(self, user_id: str, device_name: Optional[str] = None, app_version: str = "0.1.0") -> RegisteredDevice:
        return self.device_registry.register(user_id, build_local_device_info(device_name=device_name, app_version=app_version))

    def get_entitlements(self):
        state = self.current_state()
        if not state.user or not state.session:
            return {}
        return self.entitlements.get_entitlements(state.user.id, state.session.device_id)

    def record_usage(self, event_type: str, quantity: int = 1, metadata: Optional[dict] = None) -> None:
        state = self.current_state()
        self.usage_events.append(
            {
                "user_id": state.user.id if state.user else None,
                "device_id": state.session.device_id if state.session else None,
                "event_type": event_type,
                "quantity": max(1, int(quantity)),
                "metadata_json": metadata or {},
                "created_at": datetime.utcnow().isoformat(),
                "mock": True,
            }
        )

    def _new_session(self, user_id: str, device_id: str) -> AuthSession:
        issued_at = datetime.utcnow()
        suffix = int(issued_at.timestamp())
        return AuthSession(
            user_id=user_id,
            device_id=device_id,
            access_token=f"mock_access_{user_id}_{device_id}_{suffix}",
            refresh_token=f"mock_refresh_{user_id}_{device_id}_{suffix}",
            expires_at=issued_at + timedelta(minutes=self.session_minutes),
            is_mock=True,
        )

    def _mock_user_id(self, email: str) -> str:
        safe = "".join(ch if ch.isalnum() else "_" for ch in email.lower()).strip("_")
        return f"mock_user_{safe or 'demo'}"

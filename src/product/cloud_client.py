from typing import Any, Dict, Optional, Protocol

import httpx

from src.cloud.config import CLOUD_PORT
from src.product.account import UserAccount
from src.product.auth_service import MockAuthService
from src.product.auth_state import AuthState
from src.product.device import RegisteredDevice
from src.product.entitlements import PlanEntitlement
from src.product.token_store import TokenBundle


class CloudClient(Protocol):
    """Future cloud backend client interface.

    This scaffold must not perform network calls in the local MVP.
    """

    def current_user(self) -> UserAccount:
        ...

    def register_device(self, device_name: str, os_name: str, app_version: str) -> RegisteredDevice:
        ...

    def get_entitlements(self, user_id: str, device_id: str) -> Dict[str, PlanEntitlement]:
        ...

    def record_usage(self, user_id: str, device_id: str, event_type: str, quantity: int = 1) -> None:
        ...


class CloudAuthClient(Protocol):
    """Future network-backed auth client interface.

    Implementations may call the development cloud backend or a production
    backend later. The local MVP does not instantiate this interface by
    default.
    """

    def dev_login(self, email: str, name: str = "Demo User", plan: str = "free") -> Dict[str, Any]:
        ...

    def refresh(self, refresh_token: str) -> Dict[str, Any]:
        ...

    def get_me(self, access_token: str) -> Dict[str, Any]:
        ...

    def register_device(
        self,
        access_token: str,
        device_name: str,
        os_name: str,
        app_version: str,
        device_fingerprint_hash: str,
    ) -> Dict[str, Any]:
        ...

    def get_entitlements(self, access_token: str) -> Dict[str, Any]:
        ...

    def record_usage_event(
        self,
        access_token: str,
        event_type: str,
        quantity: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...


class MockCloudClient:
    """Network-free cloud client boundary used only for local tests."""

    def __init__(self, plan: str = "free"):
        self.auth = MockAuthService(plan=plan)
        self.state = self.auth.login()

    def current_user(self) -> UserAccount:
        user = self.state.user
        return UserAccount(id=user.id, email=user.email, name=user.name, status=user.status) if user else UserAccount(id="mock_user_demo", email="demo@lumos.local")

    def register_device(
        self,
        access_token: str = "",
        device_name: str = "Demo PC",
        os_name: str = "Windows",
        app_version: str = "0.1.0",
        device_fingerprint_hash: str = "",
    ) -> RegisteredDevice:
        user = self.state.user or self.auth.login().user
        return self.auth.device_registry.register(
            user.id,
            {
                "device_name": device_name,
                "os": os_name,
                "app_version": app_version,
                "device_fingerprint_hash": device_fingerprint_hash or f"mock_cloud_{device_name}_{os_name}_{app_version}",
            },
        )

    def get_entitlements(self, user_id: str = "", device_id: str = "", access_token: str = "") -> Dict[str, PlanEntitlement]:
        if not user_id or not device_id:
            state = self.auth.current_state()
            user_id = state.user.id if state.user else "mock_user_demo"
            device_id = state.session.device_id if state.session else "mock_device_demo"
        return self.auth.entitlements.get_entitlements(user_id, device_id)

    def record_usage(self, user_id: str, device_id: str, event_type: str, quantity: int = 1) -> None:
        self.auth.record_usage(event_type=event_type, quantity=quantity, metadata={"client": "mock_cloud"})

    def dev_login(self, email: str = "demo@lumos.local", name: str = "Demo User", plan: str = "free") -> Dict[str, Any]:
        self.auth = MockAuthService(plan=plan)
        self.state = self.auth.login(email=email, name=name)
        return self._token_response(self.state)

    def refresh(self, refresh_token: str = "") -> Dict[str, Any]:
        self.state = self.auth.refresh()
        return self._token_response(self.state)

    def get_me(self, access_token: str = "") -> Dict[str, Any]:
        state = self.auth.current_state()
        user = state.user
        session = state.session
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "plan": user.plan,
                "status": user.status,
            }
            if user
            else None,
            "session": {
                "device_id": session.device_id,
                "expires_at": session.expires_at.isoformat(),
            }
            if session
            else None,
            "mock": True,
        }

    def record_usage_event(
        self,
        access_token: str = "",
        event_type: str = "signal_generated",
        quantity: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.auth.record_usage(event_type=event_type, quantity=quantity, metadata=metadata or {"client": "mock_cloud"})
        return {"success": True, "event_id": f"mock_usage_{len(self.auth.usage_events)}", "mock": True}

    def _token_response(self, state: AuthState) -> Dict[str, Any]:
        user = state.user
        session = state.session
        return {
            "access_token": session.access_token if session else "",
            "refresh_token": session.refresh_token if session else "",
            "token_type": "bearer",
            "expires_in": self.auth.session_minutes * 60,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "plan": user.plan,
                "status": user.status,
            }
            if user
            else None,
            "mock": True,
        }


class CloudClientError(RuntimeError):
    def __init__(self, message: str, user_message: str = "Cloud backend에 연결할 수 없어요."):
        super().__init__(message)
        self.user_message = user_message


class DevCloudAuthClient:
    """HTTP client for the development cloud backend.

    This is only used by explicit dev connection tests. The local MVP must not
    instantiate it during normal startup.
    """

    def __init__(self, base_url: str = "", timeout_seconds: float = 3.0):
        self.base_url = (base_url or f"http://127.0.0.1:{CLOUD_PORT}").rstrip("/")
        self.timeout_seconds = timeout_seconds

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health")

    def dev_login(self, email: str, name: str = "Demo User", plan: str = "free") -> Dict[str, Any]:
        return self._request("POST", "/auth/dev-login", json={"email": email, "name": name, "plan": plan})

    def logout(self, access_token: str) -> Dict[str, Any]:
        return self._request("POST", "/auth/logout", access_token=access_token)

    def refresh(self, refresh_token: str) -> Dict[str, Any]:
        return self._request("POST", "/auth/refresh", json={"refresh_token": refresh_token})

    def get_me(self, access_token: str) -> Dict[str, Any]:
        return self._request("GET", "/auth/me", access_token=access_token)

    def register_device(
        self,
        access_token: str,
        device_name: str,
        os_name: str,
        app_version: str,
        device_fingerprint_hash: str,
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/devices/register",
            access_token=access_token,
            json={
                "device_name": device_name,
                "os": os_name,
                "app_version": app_version,
                "device_fingerprint_hash": device_fingerprint_hash,
            },
        )

    def get_entitlements(self, access_token: str) -> Dict[str, Any]:
        return self._request("GET", "/entitlements/me", access_token=access_token)

    def record_usage_event(
        self,
        access_token: str,
        event_type: str,
        quantity: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/usage/events",
            access_token=access_token,
            json={"event_type": event_type, "quantity": quantity, "metadata": metadata or {}},
        )

    def token_bundle_from_response(self, response: Dict[str, Any], device_id: str = "") -> TokenBundle:
        user = response.get("user") or {}
        return TokenBundle(
            access_token=response.get("access_token", ""),
            refresh_token=response.get("refresh_token", ""),
            token_type=response.get("token_type", "bearer"),
            expires_at=response.get("expires_at", ""),
            user_id=user.get("id", ""),
            device_id=device_id,
            is_dev=True,
        )

    def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        access_token: str = "",
    ) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise CloudClientError(
                f"cloud status error: {exc.response.status_code}",
                "Cloud 연결 확인 중 인증 또는 세션 오류가 발생했어요.",
            ) from exc
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            raise CloudClientError(
                str(exc),
                "Cloud backend가 실행 중인지 확인해 주세요: python run.py cloud",
            ) from exc

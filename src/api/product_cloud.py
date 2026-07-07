import os
import platform
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src.cloud.config import CLOUD_PORT
from src.product.cloud_client import CloudClientError, DevCloudAuthClient
from src.product.device import placeholder_device_fingerprint
from src.product.entitlement_cache import EntitlementSnapshot, InMemoryEntitlementCache, human_entitlement_summary
from src.product.token_store import InMemoryTokenStore, TokenBundle, TokenStore, TokenStoreUnavailable, build_secure_token_store

router = APIRouter(prefix="/product/cloud", tags=["product-cloud-dev"])

DEFAULT_CLOUD_BASE_URL = f"http://127.0.0.1:{CLOUD_PORT}"


class DevConnectRequest(BaseModel):
    email: str = "demo@lumos.local"
    name: str = "Demo User"
    plan: str = "pro"
    cloud_base_url: Optional[str] = None


@dataclass
class DevCloudState:
    mode: str = "local"
    connected: bool = False
    cloud_base_url: str = DEFAULT_CLOUD_BASE_URL
    access_token: str = ""
    refresh_token: str = ""
    user: Optional[Dict[str, Any]] = None
    device: Optional[Dict[str, Any]] = None
    entitlements: Dict[str, Any] = field(default_factory=dict)
    plan: str = "local"
    last_checked_at: Optional[str] = None
    message: str = "현재는 로컬 모드로 사용 중이에요."
    error_code: Optional[str] = None


_STATE = DevCloudState()
_LOCK = threading.Lock()
_MEMORY_TOKEN_STORE = InMemoryTokenStore()
_TOKEN_STORE: Optional[TokenStore] = None
_TOKEN_STORE_BACKEND = "memory"
_ENTITLEMENT_CACHE = InMemoryEntitlementCache()


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _public_state(message: Optional[str] = None) -> Dict[str, Any]:
    cache_status = _ENTITLEMENT_CACHE.describe_status()
    return {
        "mode": _STATE.mode,
        "connected": _STATE.connected,
        "cloud_base_url": _STATE.cloud_base_url,
        "user": _STATE.user,
        "device": _STATE.device,
        "plan": _STATE.plan,
        "entitlements": _STATE.entitlements,
        "entitlement_summary": human_entitlement_summary(_STATE.entitlements),
        "entitlement_cache": cache_status,
        "last_checked_at": _STATE.last_checked_at,
        "message": message or _STATE.message,
        "error_code": _STATE.error_code,
        "token_storage": _TOKEN_STORE_BACKEND,
        "dev_only": True,
    }


def _local_state(message: str = "현재는 로컬 모드로 사용 중이에요.", error_code: Optional[str] = None) -> Dict[str, Any]:
    with _LOCK:
        snapshot = _ENTITLEMENT_CACHE.load_snapshot()
        cache_status = _ENTITLEMENT_CACHE.describe_status()
        use_cached = cache_status["status"] in {"valid", "grace"}
        entitlements = snapshot.entitlements if snapshot and use_cached else {}
        return {
            "mode": "local",
            "connected": False,
            "cloud_base_url": _STATE.cloud_base_url,
            "user": None,
            "device": None,
            "plan": snapshot.plan if snapshot and use_cached else "local",
            "entitlements": entitlements,
            "entitlement_summary": human_entitlement_summary(entitlements) if entitlements else {},
            "entitlement_cache": cache_status,
            "last_checked_at": _STATE.last_checked_at,
            "message": message,
            "error_code": error_code,
            "token_storage": _TOKEN_STORE_BACKEND,
            "dev_only": True,
        }


def _reset_state(message: str = "로컬 모드로 돌아왔어요.") -> Dict[str, Any]:
    global _STATE
    with _LOCK:
        cloud_base_url = _STATE.cloud_base_url
        _STATE = DevCloudState(cloud_base_url=cloud_base_url, last_checked_at=_now(), message=message)
        return _public_state(message)


@router.get("/status")
def cloud_status():
    if not _STATE.connected:
        return _local_state()
    with _LOCK:
        return _public_state()


@router.get("/account")
def cloud_account():
    if not _STATE.connected:
        return _local_state()
    with _LOCK:
        return _public_state()


@router.post("/dev-connect")
def dev_connect(request: DevConnectRequest):
    cloud_base_url = (request.cloud_base_url or DEFAULT_CLOUD_BASE_URL).rstrip("/")
    client = DevCloudAuthClient(base_url=cloud_base_url)
    try:
        client.health()
        login = client.dev_login(email=request.email, name=request.name, plan=request.plan)
        access_token = login["access_token"]
        me = client.get_me(access_token)
        device_name = platform.node() or "Local Device"
        os_name = platform.system() or "Unknown"
        app_version = "0.1.0"
        fingerprint = placeholder_device_fingerprint(f"dev-cloud:{device_name}:{os_name}:{app_version}")
        device = client.register_device(
            access_token,
            device_name=device_name,
            os_name=os_name,
            app_version=app_version,
            device_fingerprint_hash=fingerprint,
        )
        entitlements = client.get_entitlements(access_token)
    except CloudClientError as exc:
        return _local_state(exc.user_message, error_code="cloud_unavailable")

    with _LOCK:
        _STATE.mode = "cloud_dev"
        _STATE.connected = True
        _STATE.cloud_base_url = cloud_base_url
        _STATE.access_token = access_token
        _STATE.refresh_token = login["refresh_token"]
        _STATE.user = me.get("user") or login.get("user")
        _STATE.device = device
        _STATE.plan = entitlements.get("plan") or (_STATE.user or {}).get("plan") or "free"
        _STATE.entitlements = entitlements.get("entitlements") or {}
        _ENTITLEMENT_CACHE.save_snapshot(
            EntitlementSnapshot.from_cloud_response(
                user_id=(_STATE.user or {}).get("id", ""),
                device_id=device.get("id", ""),
                response=entitlements,
            )
        )
        _STATE.last_checked_at = _now()
        _STATE.message = "개발용 cloud 연결이 확인됐어요."
        _STATE.error_code = None
        _save_dev_tokens(
            TokenBundle(
                access_token=access_token,
                refresh_token=login["refresh_token"],
                token_type=login.get("token_type", "bearer"),
                user_id=(_STATE.user or {}).get("id", ""),
                device_id=device.get("id", ""),
                is_dev=True,
            )
        )
        return _public_state(_STATE.message)


@router.post("/dev-disconnect")
def dev_disconnect():
    access_token = ""
    cloud_base_url = DEFAULT_CLOUD_BASE_URL
    with _LOCK:
        access_token = _STATE.access_token
        cloud_base_url = _STATE.cloud_base_url
    if access_token:
        try:
            DevCloudAuthClient(base_url=cloud_base_url).logout(access_token)
        except CloudClientError:
            pass
    _clear_dev_tokens()
    _ENTITLEMENT_CACHE.clear_snapshot()
    return _reset_state()


@router.post("/usage-test")
def usage_test():
    with _LOCK:
        if not _STATE.connected or not _STATE.access_token:
            return _local_state("먼저 개발용 cloud 연결 테스트를 실행해 주세요.", error_code="auth_required")
        access_token = _STATE.access_token
        cloud_base_url = _STATE.cloud_base_url
    try:
        result = DevCloudAuthClient(base_url=cloud_base_url).record_usage_event(
            access_token,
            event_type="dev_connection_test",
            quantity=1,
            metadata={"surface": "settings_account_shell"},
        )
    except CloudClientError as exc:
        return _local_state(exc.user_message, error_code="cloud_unavailable")
    with _LOCK:
        _STATE.last_checked_at = _now()
        _STATE.message = "사용량 이벤트 테스트를 보냈어요."
        response = _public_state(_STATE.message)
        response["usage_event"] = result
        return response


def _token_store() -> TokenStore:
    global _TOKEN_STORE, _TOKEN_STORE_BACKEND
    if _TOKEN_STORE is not None:
        return _TOKEN_STORE
    if os.getenv("LUMOS_DEV_PERSIST_TOKENS") == "1":
        try:
            _TOKEN_STORE = build_secure_token_store(username="dev-cloud")
            _TOKEN_STORE_BACKEND = _TOKEN_STORE.describe_backend()
            return _TOKEN_STORE
        except TokenStoreUnavailable:
            _TOKEN_STORE_BACKEND = "keyring_unavailable_memory"
    else:
        _TOKEN_STORE_BACKEND = "memory"
    _TOKEN_STORE = _MEMORY_TOKEN_STORE
    return _TOKEN_STORE


def _save_dev_tokens(bundle: TokenBundle) -> None:
    try:
        _token_store().save_tokens(bundle)
    except TokenStoreUnavailable:
        _MEMORY_TOKEN_STORE.save_tokens(bundle)


def _clear_dev_tokens() -> None:
    try:
        _token_store().clear_tokens()
    except TokenStoreUnavailable:
        pass
    _MEMORY_TOKEN_STORE.clear_tokens()


def current_feature_gate_context() -> Dict[str, Any]:
    with _LOCK:
        snapshot = _ENTITLEMENT_CACHE.load_snapshot()
        cache_status = _ENTITLEMENT_CACHE.describe_status()
        use_cached = snapshot is not None and cache_status["status"] in {"valid", "grace"}
        plan = _STATE.plan if _STATE.connected else (snapshot.plan if use_cached else "local_mvp")
        entitlements = _STATE.entitlements if _STATE.connected else (snapshot.entitlements if use_cached else {})
        return {
            "mode": _STATE.mode if _STATE.connected else "local",
            "plan": plan or "local_mvp",
            "entitlements": entitlements,
            "cache_status": cache_status,
            "is_dev": True,
            "is_enforced": False,
        }

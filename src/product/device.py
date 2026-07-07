import hashlib
import platform
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional


@dataclass(frozen=True)
class RegisteredDevice:
    """Future registered local app installation.

    TODO: add device registration and license checks in a later phase.
    """

    id: str
    user_id: str
    device_name: str
    os: str
    app_version: str
    device_fingerprint_hash: str
    registered_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    status: str = "active"


def placeholder_device_fingerprint(seed: str) -> str:
    """Return a non-production placeholder hash for future device registration tests."""

    return hashlib.sha256(f"mock-device:{seed}".encode("utf-8")).hexdigest()


def build_local_device_info(device_name: Optional[str] = None, app_version: str = "0.1.0") -> Dict[str, str]:
    """Build minimal local device metadata without collecting invasive identifiers."""

    name = device_name or platform.node() or "Local Device"
    os_name = platform.system() or "Unknown"
    return {
        "device_name": name,
        "os": os_name,
        "app_version": app_version,
        "device_fingerprint_hash": placeholder_device_fingerprint(f"{name}:{os_name}:{app_version}"),
    }


class MockDeviceRegistry:
    """In-memory device registry for auth boundary tests."""

    def __init__(self):
        self._devices: Dict[str, RegisteredDevice] = {}

    def register(self, user_id: str, device_info: Dict[str, str]) -> RegisteredDevice:
        fingerprint = device_info.get("device_fingerprint_hash") or placeholder_device_fingerprint(user_id)
        device_id = f"mock_device_{fingerprint[:12]}"
        now = datetime.utcnow()
        device = RegisteredDevice(
            id=device_id,
            user_id=user_id,
            device_name=device_info.get("device_name", "Local Device"),
            os=device_info.get("os", "Unknown"),
            app_version=device_info.get("app_version", "0.1.0"),
            device_fingerprint_hash=fingerprint,
            registered_at=self._devices.get(device_id, RegisteredDevice(device_id, user_id, "", "", "", "")).registered_at or now,
            last_seen_at=now,
            status="active",
        )
        self._devices[device_id] = device
        return device

    def list_for_user(self, user_id: str):
        return [device for device in self._devices.values() if device.user_id == user_id]

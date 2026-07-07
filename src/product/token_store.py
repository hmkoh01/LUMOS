import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Protocol


class TokenStoreBackend(str, Enum):
    MEMORY = "memory"
    KEYRING = "keyring"
    UNAVAILABLE = "unavailable"


class TokenStoreError(RuntimeError):
    pass


class TokenStoreUnavailable(TokenStoreError):
    pass


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: str = ""
    user_id: str = ""
    device_id: str = ""
    is_dev: bool = False
    stored_at: str = ""

    def __post_init__(self):
        if not self.stored_at:
            self.stored_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    def __repr__(self) -> str:
        return (
            "TokenBundle("
            f"token_type={self.token_type!r}, expires_at={self.expires_at!r}, "
            f"user_id={self.user_id!r}, device_id={self.device_id!r}, "
            f"is_dev={self.is_dev!r}, stored_at={self.stored_at!r}, "
            "access_token=<redacted>, refresh_token=<redacted>)"
        )

    __str__ = __repr__

    def to_json(self) -> str:
        return json.dumps(
            {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "token_type": self.token_type,
                "expires_at": self.expires_at,
                "user_id": self.user_id,
                "device_id": self.device_id,
                "is_dev": self.is_dev,
                "stored_at": self.stored_at,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, payload: str) -> "TokenBundle":
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise TokenStoreError("Stored token payload is not valid JSON.") from exc
        return cls(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            token_type=data.get("token_type", "bearer"),
            expires_at=data.get("expires_at", ""),
            user_id=data.get("user_id", ""),
            device_id=data.get("device_id", ""),
            is_dev=bool(data.get("is_dev", False)),
            stored_at=data.get("stored_at", ""),
        )


class TokenStore(Protocol):
    def save_tokens(self, bundle: TokenBundle) -> None:
        ...

    def load_tokens(self) -> Optional[TokenBundle]:
        ...

    def clear_tokens(self) -> None:
        ...

    def has_tokens(self) -> bool:
        ...

    def describe_backend(self) -> str:
        ...


class InMemoryTokenStore:
    def __init__(self):
        self._bundle: Optional[TokenBundle] = None

    def save_tokens(self, bundle: TokenBundle) -> None:
        self._bundle = bundle

    def load_tokens(self) -> Optional[TokenBundle]:
        return self._bundle

    def clear_tokens(self) -> None:
        self._bundle = None

    def has_tokens(self) -> bool:
        return self._bundle is not None

    def describe_backend(self) -> str:
        return TokenStoreBackend.MEMORY.value


class KeyringTokenStore:
    def __init__(self, service_name: str = "LUMOS", username: str = "default"):
        self.service_name = service_name
        self.username = username
        try:
            import keyring  # type: ignore
        except Exception as exc:
            raise TokenStoreUnavailable("keyring is not available in this environment.") from exc
        self._keyring = keyring

    def save_tokens(self, bundle: TokenBundle) -> None:
        try:
            self._keyring.set_password(self.service_name, self.username, bundle.to_json())
        except Exception as exc:
            raise TokenStoreUnavailable("keyring token save failed.") from exc

    def load_tokens(self) -> Optional[TokenBundle]:
        try:
            payload = self._keyring.get_password(self.service_name, self.username)
        except Exception as exc:
            raise TokenStoreUnavailable("keyring token load failed.") from exc
        if not payload:
            return None
        return TokenBundle.from_json(payload)

    def clear_tokens(self) -> None:
        try:
            self._keyring.delete_password(self.service_name, self.username)
        except Exception:
            return

    def has_tokens(self) -> bool:
        return self.load_tokens() is not None

    def describe_backend(self) -> str:
        return TokenStoreBackend.KEYRING.value


def build_secure_token_store(username: str = "default") -> TokenStore:
    return KeyringTokenStore(username=username)


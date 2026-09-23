from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional, Protocol


DEFAULT_CACHE_TTL_HOURS = 24
DEFAULT_OFFLINE_GRACE_DAYS = 7


class EntitlementCacheStatus(str, Enum):
    EMPTY = "empty"
    VALID = "valid"
    GRACE = "grace"
    EXPIRED = "expired"


class OfflineGraceDecision(str, Enum):
    USE_CLOUD = "use_cloud"
    USE_CACHE = "use_cache"
    USE_GRACE = "use_grace"
    FALLBACK_LOCAL = "fallback_local"


def utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def parse_time(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip("Z"))
    except ValueError:
        return None


def format_time(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat() + "Z"


@dataclass
class EntitlementSnapshot:
    user_id: str
    device_id: str
    plan: str
    entitlements: Dict[str, Any]
    fetched_at: str
    expires_at: str
    grace_until: str
    source: str = "cloud_dev"
    is_dev: bool = True
    last_successful_check_at: str = ""

    @classmethod
    def from_cloud_response(
        cls,
        user_id: str,
        device_id: str,
        response: Dict[str, Any],
        now: Optional[datetime] = None,
        ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
        grace_days: int = DEFAULT_OFFLINE_GRACE_DAYS,
    ) -> "EntitlementSnapshot":
        current = now or utc_now()
        fetched = response.get("fetched_at") or format_time(current)
        expires = response.get("expires_at") or format_time(current + timedelta(hours=ttl_hours))
        grace = response.get("grace_until") or format_time(current + timedelta(days=grace_days))
        return cls(
            user_id=user_id,
            device_id=device_id,
            plan=response.get("plan", "free"),
            entitlements=response.get("entitlements") or {},
            fetched_at=fetched,
            expires_at=expires,
            grace_until=grace,
            source=response.get("source", "cloud_dev"),
            is_dev=bool(response.get("is_dev", True)),
            last_successful_check_at=fetched,
        )

    def status(self, now: Optional[datetime] = None) -> EntitlementCacheStatus:
        current = now or utc_now()
        expires = parse_time(self.expires_at)
        grace = parse_time(self.grace_until)
        if expires and current <= expires:
            return EntitlementCacheStatus.VALID
        if grace and current <= grace:
            return EntitlementCacheStatus.GRACE
        return EntitlementCacheStatus.EXPIRED


class EntitlementCache(Protocol):
    def save_snapshot(self, snapshot: EntitlementSnapshot) -> None:
        ...

    def load_snapshot(self) -> Optional[EntitlementSnapshot]:
        ...

    def clear_snapshot(self) -> None:
        ...

    def has_valid_snapshot(self, now: Optional[datetime] = None) -> bool:
        ...

    def evaluate_offline_grace(self, now: Optional[datetime] = None) -> OfflineGraceDecision:
        ...

    def describe_status(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        ...


class InMemoryEntitlementCache:
    def __init__(self):
        self._snapshot: Optional[EntitlementSnapshot] = None

    def save_snapshot(self, snapshot: EntitlementSnapshot) -> None:
        self._snapshot = snapshot

    def load_snapshot(self) -> Optional[EntitlementSnapshot]:
        return self._snapshot

    def clear_snapshot(self) -> None:
        self._snapshot = None

    def has_valid_snapshot(self, now: Optional[datetime] = None) -> bool:
        return self.evaluate_offline_grace(now) in {
            OfflineGraceDecision.USE_CACHE,
            OfflineGraceDecision.USE_CLOUD,
        }

    def evaluate_offline_grace(self, now: Optional[datetime] = None) -> OfflineGraceDecision:
        if not self._snapshot:
            return OfflineGraceDecision.FALLBACK_LOCAL
        status = self._snapshot.status(now)
        if status == EntitlementCacheStatus.VALID:
            return OfflineGraceDecision.USE_CACHE
        if status == EntitlementCacheStatus.GRACE:
            return OfflineGraceDecision.USE_GRACE
        return OfflineGraceDecision.FALLBACK_LOCAL

    def describe_status(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        if not self._snapshot:
            return {
                "status": EntitlementCacheStatus.EMPTY.value,
                "decision": OfflineGraceDecision.FALLBACK_LOCAL.value,
                "message": "권한 cache가 아직 없어요.",
            }
        status = self._snapshot.status(now)
        decision = self.evaluate_offline_grace(now)
        return {
            "status": status.value,
            "decision": decision.value,
            "plan": self._snapshot.plan,
            "fetched_at": self._snapshot.fetched_at,
            "expires_at": self._snapshot.expires_at,
            "grace_until": self._snapshot.grace_until,
            "source": self._snapshot.source,
            "is_dev": self._snapshot.is_dev,
            "message": cache_status_message(status),
        }


def cache_status_message(status: EntitlementCacheStatus) -> str:
    if status == EntitlementCacheStatus.VALID:
        return "권한 확인: Cloud에서 확인된 권한을 사용 중이에요."
    if status == EntitlementCacheStatus.GRACE:
        return "권한 확인: Offline grace 적용 중이에요."
    if status == EntitlementCacheStatus.EXPIRED:
        return "권한 확인: 만료됨 · 로컬 모드로 사용 중이에요."
    return "권한 확인: 로컬 모드로 사용 중이에요."


def human_entitlement_summary(entitlements: Dict[str, Any]) -> Dict[str, str]:
    return {
        "daily_signals": f"오늘 소식 {entitlements.get('max_signals_per_day', '-')}개",
        "sources": f"소스 {entitlements.get('max_sources', '-')}개",
        "auto_briefing": "자동 브리핑 가능" if entitlements.get("auto_briefing_enabled") else "자동 브리핑 제한",
        "context": "개인 맥락 connector 가능" if entitlements.get("context_connectors_enabled") else "개인 맥락 connector 제한",
        "history": f"기록 {entitlements.get('history_days', '-')}일",
        "team": "팀 workspace 가능" if entitlements.get("team_workspace_enabled") else "개인 workspace",
    }


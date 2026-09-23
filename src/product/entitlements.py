from dataclasses import dataclass
from typing import Dict, Optional, Protocol


@dataclass(frozen=True)
class PlanEntitlement:
    """A plan-derived permission or usage limit."""

    key: str
    value: str
    description: str = ""


FREE_ENTITLEMENTS: Dict[str, PlanEntitlement] = {
    "max_signals_per_day": PlanEntitlement("max_signals_per_day", "3", "하루에 받을 수 있는 소식 수"),
    "max_sources": PlanEntitlement("max_sources", "3", "기본 소스 수"),
    "auto_briefing_enabled": PlanEntitlement("auto_briefing_enabled", "false", "자동 브리핑"),
    "advanced_sources_enabled": PlanEntitlement("advanced_sources_enabled", "false", "고급 소스"),
    "context_connectors_enabled": PlanEntitlement("context_connectors_enabled", "false", "개인 맥락 connector"),
    "history_days": PlanEntitlement("history_days", "7", "보관 기간"),
    "team_workspace_enabled": PlanEntitlement("team_workspace_enabled", "false", "팀 workspace"),
}

PRO_ENTITLEMENTS: Dict[str, PlanEntitlement] = {
    **FREE_ENTITLEMENTS,
    "max_signals_per_day": PlanEntitlement("max_signals_per_day", "10", "Pro 하루 소식 수"),
    "max_sources": PlanEntitlement("max_sources", "8", "Pro 소스 수"),
    "auto_briefing_enabled": PlanEntitlement("auto_briefing_enabled", "true", "자동 브리핑"),
    "advanced_sources_enabled": PlanEntitlement("advanced_sources_enabled", "true", "고급 소스"),
    "context_connectors_enabled": PlanEntitlement("context_connectors_enabled", "true", "개인 맥락 connector"),
    "history_days": PlanEntitlement("history_days", "90", "Pro 보관 기간"),
}

TEAM_ENTITLEMENTS: Dict[str, PlanEntitlement] = {
    **PRO_ENTITLEMENTS,
    "team_workspace_enabled": PlanEntitlement("team_workspace_enabled", "true", "팀 workspace"),
}


class EntitlementService(Protocol):
    """Interface for future plan checks.

    TODO: implement cloud-backed entitlement validation after account/device auth.
    """

    def get_entitlements(self, user_id: str, device_id: str) -> Dict[str, PlanEntitlement]:
        ...

    def is_allowed(self, user_id: str, device_id: str, entitlement_key: str, quantity: int = 1) -> bool:
        ...


@dataclass
class StaticEntitlementService:
    """Local-only test implementation for future unit tests, not product runtime."""

    entitlements: Dict[str, PlanEntitlement]

    def get_entitlements(self, user_id: str, device_id: str) -> Dict[str, PlanEntitlement]:
        return dict(self.entitlements)

    def is_allowed(self, user_id: str, device_id: str, entitlement_key: str, quantity: int = 1) -> bool:
        entitlement: Optional[PlanEntitlement] = self.entitlements.get(entitlement_key)
        if not entitlement:
            return False
        try:
            return quantity <= int(entitlement.value)
        except ValueError:
            return entitlement.value.lower() in {"true", "enabled", "yes"}


class MockEntitlementService:
    """Plan-based entitlement service with no network calls."""

    def __init__(self, plan: str = "free"):
        self.plan = self.normalize_plan(plan)

    def get_entitlements(self, user_id: str, device_id: str) -> Dict[str, PlanEntitlement]:
        if self.plan == "pro":
            return dict(PRO_ENTITLEMENTS)
        if self.plan == "team":
            return dict(TEAM_ENTITLEMENTS)
        return dict(FREE_ENTITLEMENTS)

    def is_allowed(self, user_id: str, device_id: str, entitlement_key: str, quantity: int = 1) -> bool:
        return StaticEntitlementService(self.get_entitlements(user_id, device_id)).is_allowed(
            user_id,
            device_id,
            entitlement_key,
            quantity=quantity,
        )

    def normalize_plan(self, plan: str) -> str:
        return plan if plan in {"free", "pro", "team"} else "free"

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class FeatureKey(str, Enum):
    TODAY_SIGNAL_COUNT = "today_signal_count"
    DAILY_GENERATE_LIMIT = "daily_generate_limit"
    SOURCE_COUNT = "source_count"
    AUTO_BRIEFING = "auto_briefing"
    ADVANCED_SOURCES = "advanced_sources"
    CONTEXT_CONNECTORS = "context_connectors"
    HISTORY_RETENTION = "history_retention"
    TEAM_WORKSPACE = "team_workspace"
    CLOUD_SYNC = "cloud_sync"
    EXPORT_SHARE = "export_share"


class GateSeverity(str, Enum):
    ALLOWED = "allowed"
    SOFT_LIMIT = "soft_limit"
    UPGRADE_RECOMMENDED = "upgrade_recommended"
    UNAVAILABLE_FUTURE = "unavailable_future"
    HARD_BLOCK_FUTURE = "hard_block_future"


@dataclass
class GateDecision:
    feature_key: str
    allowed: bool
    severity: str
    plan: str
    required_plan: str = ""
    current_value: Optional[Any] = None
    limit_value: Optional[Any] = None
    message_ko: str = ""
    upgrade_hint_ko: str = ""
    is_dev: bool = True
    is_enforced: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_key": self.feature_key,
            "allowed": self.allowed,
            "severity": self.severity,
            "plan": self.plan,
            "required_plan": self.required_plan,
            "current_value": self.current_value,
            "limit_value": self.limit_value,
            "message_ko": self.message_ko,
            "upgrade_hint_ko": self.upgrade_hint_ko,
            "is_dev": self.is_dev,
            "is_enforced": self.is_enforced,
        }


@dataclass
class FeatureGateContext:
    plan: str = "local_mvp"
    entitlements: Dict[str, Any] = field(default_factory=dict)
    cache_status: str = "empty"
    cache_decision: str = "fallback_local"
    is_dev: bool = True
    is_enforced: bool = False


class StaticFeatureGateService:
    """Soft gate evaluator.

    This service intentionally does not block the local MVP. It returns
    decisions that can become hard gates after production auth/billing exists.
    """

    def evaluate(
        self,
        context: FeatureGateContext,
        feature_key: str,
        current_value: Optional[Any] = None,
    ) -> GateDecision:
        key = normalize_feature_key(feature_key)
        plan = normalize_plan(context.plan)
        entitlements = entitlements_for_context(context, plan)
        cache_prefix = cache_message_prefix(context)

        if key == FeatureKey.TODAY_SIGNAL_COUNT:
            limit = int(entitlements.get("max_signals_per_day", 3))
            if current_value is not None and int(current_value) > limit:
                return GateDecision(
                    key.value,
                    True,
                    GateSeverity.UPGRADE_RECOMMENDED.value,
                    plan,
                    required_plan="pro",
                    current_value=current_value,
                    limit_value=limit,
                    message_ko=f"{cache_prefix}현재는 제한하지 않지만, {plan_label(plan)} 기준보다 많은 소식을 요청했어요.",
                    upgrade_hint_ko="Pro에서는 더 많은 오늘의 소식을 제공하도록 설계 중이에요.",
                    is_dev=context.is_dev,
                    is_enforced=False,
                )
            return self._allowed(key, plan, f"{cache_prefix}{plan_label(plan)} 기준 오늘의 소식는 {limit}개까지가 기본이에요.", limit)

        if key == FeatureKey.SOURCE_COUNT:
            limit = int(entitlements.get("max_sources", 3))
            if current_value is not None and int(current_value) > limit:
                return GateDecision(
                    key.value,
                    True,
                    GateSeverity.SOFT_LIMIT.value,
                    plan,
                    required_plan="pro",
                    current_value=current_value,
                    limit_value=limit,
                    message_ko=f"{cache_prefix}향후 {plan_label(plan)} 기준에서는 source 수가 제한될 수 있어요.",
                    upgrade_hint_ko="Pro에서는 더 많은 source를 연결하는 방향으로 설계 중이에요.",
                    is_dev=context.is_dev,
                    is_enforced=False,
                )
            return self._allowed(key, plan, f"{cache_prefix}{plan_label(plan)} 기준 source {limit}개까지가 기본이에요.", limit)

        boolean_features = {
            FeatureKey.AUTO_BRIEFING: ("auto_briefing_enabled", "pro", "자동 브리핑"),
            FeatureKey.ADVANCED_SOURCES: ("advanced_sources_enabled", "pro", "고급 source"),
            FeatureKey.CONTEXT_CONNECTORS: ("context_connectors_enabled", "pro", "개인 맥락 connector"),
            FeatureKey.TEAM_WORKSPACE: ("team_workspace_enabled", "team", "팀 workspace"),
        }
        if key in boolean_features:
            entitlement_key, required_plan, label = boolean_features[key]
            if entitlements.get(entitlement_key):
                return self._allowed(key, plan, f"{cache_prefix}{label} 사용 가능으로 표시돼요.")
            return GateDecision(
                key.value,
                True,
                GateSeverity.UNAVAILABLE_FUTURE.value if required_plan == "team" else GateSeverity.UPGRADE_RECOMMENDED.value,
                plan,
                required_plan=required_plan,
                message_ko=f"{cache_prefix}{label}은 향후 {plan_label(required_plan)} 기능으로 안내할 예정이에요.",
                upgrade_hint_ko="현재는 안내만 표시하고 기능을 막지 않아요.",
                is_dev=context.is_dev,
                is_enforced=False,
            )

        if key == FeatureKey.HISTORY_RETENTION:
            days = int(entitlements.get("history_days", 7))
            return self._allowed(key, plan, f"{cache_prefix}{plan_label(plan)} 기준 기록 보관 기간은 {days}일로 설계 중이에요.", days)

        if key in {FeatureKey.CLOUD_SYNC, FeatureKey.EXPORT_SHARE, FeatureKey.DAILY_GENERATE_LIMIT}:
            return GateDecision(
                key.value,
                True,
                GateSeverity.UNAVAILABLE_FUTURE.value,
                plan,
                required_plan="pro",
                current_value=current_value,
                message_ko=f"{cache_prefix}이 기능은 향후 요금제와 함께 정리할 예정이에요.",
                upgrade_hint_ko="현재 MVP에서는 기능을 막지 않아요.",
                is_dev=context.is_dev,
                is_enforced=False,
            )

        return self._allowed(key, plan, f"{cache_prefix}현재는 로컬 모드로 사용할 수 있어요.")

    def summary(self, context: FeatureGateContext) -> List[GateDecision]:
        keys = [
            FeatureKey.TODAY_SIGNAL_COUNT,
            FeatureKey.SOURCE_COUNT,
            FeatureKey.AUTO_BRIEFING,
            FeatureKey.ADVANCED_SOURCES,
            FeatureKey.CONTEXT_CONNECTORS,
            FeatureKey.HISTORY_RETENTION,
            FeatureKey.TEAM_WORKSPACE,
        ]
        return [self.evaluate(context, key.value) for key in keys]

    def _allowed(self, key: FeatureKey, plan: str, message: str, limit_value: Optional[Any] = None) -> GateDecision:
        return GateDecision(
            key.value,
            True,
            GateSeverity.ALLOWED.value,
            plan,
            limit_value=limit_value,
            message_ko=message,
            upgrade_hint_ko="현재는 안내만 표시하고 기존 기능은 계속 사용할 수 있어요.",
            is_enforced=False,
        )


def normalize_plan(plan: str) -> str:
    if plan in {"free", "pro", "team"}:
        return plan
    return "local_mvp"


def normalize_feature_key(feature_key: str) -> FeatureKey:
    try:
        return FeatureKey(feature_key)
    except ValueError:
        return FeatureKey.CLOUD_SYNC


def entitlements_for_context(context: FeatureGateContext, plan: str) -> Dict[str, Any]:
    if context.entitlements:
        return context.entitlements
    if plan == "pro":
        return {
            "max_signals_per_day": 10,
            "max_sources": 8,
            "auto_briefing_enabled": True,
            "advanced_sources_enabled": True,
            "context_connectors_enabled": True,
            "history_days": 90,
            "team_workspace_enabled": False,
        }
    if plan == "team":
        return {
            "max_signals_per_day": 10,
            "max_sources": 8,
            "auto_briefing_enabled": True,
            "advanced_sources_enabled": True,
            "context_connectors_enabled": True,
            "history_days": 90,
            "team_workspace_enabled": True,
        }
    return {
        "max_signals_per_day": 3,
        "max_sources": 3,
        "auto_briefing_enabled": False,
        "advanced_sources_enabled": False,
        "context_connectors_enabled": False,
        "history_days": 7,
        "team_workspace_enabled": False,
    }


def cache_message_prefix(context: FeatureGateContext) -> str:
    if context.cache_status == "grace":
        return "Cloud 확인이 필요하지만 offline grace 안에서 안내 중이에요. "
    if context.cache_status == "expired":
        return "권한 확인이 만료되어 로컬 모드 기준으로 안내해요. "
    if context.cache_status == "empty":
        return "아직 cloud 권한을 확인하지 않아 로컬 기준으로 안내해요. "
    return ""


def plan_label(plan: str) -> str:
    return {
        "free": "Free",
        "pro": "Pro",
        "team": "Team",
        "local_mvp": "로컬 MVP",
    }.get(plan, "Free")


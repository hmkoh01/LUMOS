"""Engine-wide configuration and limits.

All external-call and cost-related knobs live here so they can be
overridden in tests without touching multiple files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class CollectionConfig:
    """Cooperative collection settings."""
    schedule_interval_hours: int = 24
    scheduler_enabled: bool = False  # MUST be False by default
    max_concurrent_workers: int = 2
    max_items_per_source: int = 50
    backfill_on_new_user: bool = True  # design only; never auto-executed
    active_user_window_days: int = 7
    max_source_retries: int = 3
    rate_limit_delay_seconds: float = 1.0
    rate_limit_429_backoff_seconds: float = 30.0
    # OpenAlex has a free daily allowance, but LUMOS never permits a worker
    # to spill into paid usage. This is a global persisted request cap.
    openalex_max_requests_per_day: int = 10
    # Domestic sources remain disabled until an operator sets these explicit
    # per-source caps after production approval.  Zero is a hard stop.
    tourapi_max_requests_per_day: int = 0
    opendart_max_requests_per_day: int = 0
    # A company-code directory must be refreshed by a separately authorised
    # shared job; stale mappings block company disclosure collection.
    opendart_corporation_cache_max_age_hours: int = 168
    # Empty means OpenDART cannot run as a user-scoped Pilot. An operator must
    # name the small Pilot cohort explicitly; this does not affect the
    # pre-existing GitHub/HN pilot sources.
    opendart_pilot_user_ids: tuple[int, ...] = ()
    # Discovery is opt-in. The default provider is disabled and never performs
    # web searches; this flag only permits aggregated backlog maintenance.
    source_discovery_enabled: bool = False
    source_discovery_window_days: int = 7
    source_discovery_max_requests_per_day: int = 0
    # A reviewed static official directory is distinct from a general web
    # search provider.  It is opt-in because even metadata-only discovery
    # writes operational backlog rows.
    source_discovery_official_directory_enabled: bool = False
    # Real collection starts only when explicitly enabled.  New deployments
    # begin with a small allowlist until call volume is reviewed.
    pilot_sources: tuple[str, ...] = ("hackernews", "github")
    schedule_slots_kst: tuple[str, ...] = ("06:30", "18:30")


@dataclass(frozen=True)
class EvaluationConfig:
    """Period-independent importance evaluation."""
    daily_candidate_limit: int = 100
    weekly_candidate_limit: int = 200
    monthly_candidate_limit: int = 300
    min_importance_score: float = 0.1


@dataclass(frozen=True)
class LLMConfig:
    """LLM routing and caching."""
    cheap_model: str = "gemini-2.0-flash"
    expensive_model: str = "gemini-2.5-pro"
    cheap_model_max_tokens: int = 1024
    expensive_model_max_tokens: int = 2048
    cache_ttl_hours: int = 72
    max_items_per_llm_call: int = 5  # batch Korean briefing generation
    validation_confidence_threshold: float = 0.7
    expensive_model_enabled: bool = False  # disabled for free tier
    provider: str = "mock"  # mock | agent_platform; mock remains the default
    agent_platform_model: str = "gemini-3.5-flash-lite"


@dataclass(frozen=True)
class BudgetConfig:
    """Cost and usage limits for free beta."""
    # Per-user limits
    max_briefing_display_count: int = 5
    max_chat_requests_per_day: int = 10
    max_tokens_per_chat_request: int = 4096
    # Collection limits
    max_daily_collection_jobs: int = 50
    max_interest_backfill_per_user: int = 1
    # LLM generation limits
    max_daily_briefing_generations: int = 100
    max_daily_expensive_llm_calls: int = 10
    # Global budget
    daily_budget_usd: float = 5.0
    monthly_budget_usd: float = 100.0
    # Cached briefing re-display does NOT count against LLM usage
    cache_display_counts_as_usage: bool = False


@dataclass(frozen=True)
class PersonalizationConfig:
    """Recommendation and backfill settings."""
    max_reserve_candidates: int = 20
    backfill_from_reserves: bool = True
    undo_window_seconds: int = 30


@dataclass
class EngineConfig:
    """Top-level engine configuration."""
    enabled: bool = False  # Feature flag: engine is OFF by default
    external_calls_allowed: bool = False  # Hard safety: no real API calls
    collection: CollectionConfig = field(default_factory=CollectionConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    personalization: PersonalizationConfig = field(default_factory=PersonalizationConfig)

    @classmethod
    def from_env(cls) -> "EngineConfig":
        """Build config from environment variables with safe defaults."""
        return cls(
            enabled=os.environ.get("LUMOS_ENGINE_V2", "false").lower() == "true",
            external_calls_allowed=os.environ.get("LUMOS_EXTERNAL_CALLS", "false").lower() == "true",
            collection=CollectionConfig(
                scheduler_enabled=os.environ.get("LUMOS_SCHEDULER_ENABLED", "false").lower() == "true",
                pilot_sources=tuple(part.strip() for part in os.environ.get(
                    "LUMOS_ENGINE_PILOT_SOURCES", "hackernews,github"
                ).split(",") if part.strip()),
                schedule_slots_kst=tuple(part.strip() for part in os.environ.get(
                    "LUMOS_ENGINE_SCHEDULE_SLOTS_KST", "06:30,18:30"
                ).split(",") if part.strip()),
                openalex_max_requests_per_day=max(0, int(os.environ.get("LUMOS_OPENALEX_MAX_REQUESTS_PER_DAY", "10"))),
                tourapi_max_requests_per_day=max(0, int(os.environ.get("LUMOS_TOURAPI_MAX_REQUESTS_PER_DAY", "0"))),
                opendart_max_requests_per_day=max(0, int(os.environ.get("LUMOS_OPENDART_MAX_REQUESTS_PER_DAY", "0"))),
                opendart_corporation_cache_max_age_hours=max(1, int(os.environ.get("LUMOS_OPENDART_CORPORATION_CACHE_MAX_AGE_HOURS", "168"))),
                opendart_pilot_user_ids=tuple(
                    int(value.strip()) for value in os.environ.get("LUMOS_OPENDART_PILOT_USER_IDS", "").split(",")
                    if value.strip().isdigit() and int(value.strip()) > 0
                ),
                source_discovery_enabled=os.environ.get("LUMOS_SOURCE_DISCOVERY_ENABLED", "false").lower() == "true",
                source_discovery_window_days=max(1, int(os.environ.get("LUMOS_SOURCE_DISCOVERY_WINDOW_DAYS", "7"))),
                source_discovery_max_requests_per_day=max(0, int(os.environ.get("LUMOS_SOURCE_DISCOVERY_MAX_REQUESTS_PER_DAY", "0"))),
                source_discovery_official_directory_enabled=os.environ.get(
                    "LUMOS_SOURCE_DISCOVERY_OFFICIAL_DIRECTORY_ENABLED", "false"
                ).lower() == "true",
            ),
            llm=LLMConfig(
                provider=os.environ.get("LUMOS_ENGINE_LLM_PROVIDER", "mock").lower(),
                agent_platform_model=os.environ.get("LUMOS_ENGINE_AGENT_MODEL", "gemini-3.5-flash-lite"),
            ),
            budget=BudgetConfig(
                max_briefing_display_count=int(os.environ.get("LUMOS_MAX_BRIEFING_DISPLAY", "5")),
                daily_budget_usd=float(os.environ.get("LUMOS_DAILY_BUDGET_USD", "5.0")),
                monthly_budget_usd=float(os.environ.get("LUMOS_MONTHLY_BUDGET_USD", "100.0")),
            ),
        )


# Synonym dictionary for interest normalisation (rule-based, no LLM needed)
INTEREST_SYNONYMS: Dict[str, str] = {
    "artificial intelligence": "AI",
    "machine learning": "ML",
    "deep learning": "ML",
    "large language model": "LLM",
    "llm": "LLM",
    "generative ai": "생성형 AI",
    "gen ai": "생성형 AI",
    "frontend": "프론트엔드",
    "backend": "백엔드",
    "devops": "DevOps",
    "ci/cd": "CI/CD",
    "startup": "스타트업",
    "open source": "오픈소스",
    "cyber security": "사이버 보안",
    "cybersecurity": "사이버 보안",
    "fintech": "핀테크",
    "healthcare ai": "헬스케어 AI",
    "saas": "SaaS",
    "b2b saas": "B2B SaaS",
}

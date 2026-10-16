"""Plan-based limits for free/paid tiers.

Currently only the free beta tier is defined.  Paid plan specifics
are intentionally not finalised and NOT activated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.engine.config import BudgetConfig


@dataclass(frozen=True)
class PlanLimits:
    name: str
    max_briefing_display: int
    max_chat_per_day: int
    max_tokens_per_chat: int
    max_daily_collection: int
    max_daily_briefing_gen: int
    max_daily_expensive_llm: int
    daily_budget_usd: float
    monthly_budget_usd: float


FREE_BETA = PlanLimits(
    name="free_beta",
    max_briefing_display=5,
    max_chat_per_day=10,
    max_tokens_per_chat=4096,
    max_daily_collection=50,
    max_daily_briefing_gen=100,
    max_daily_expensive_llm=10,
    daily_budget_usd=5.0,
    monthly_budget_usd=100.0,
)


def plan_to_budget_config(plan: PlanLimits) -> BudgetConfig:
    """Convert a plan definition into a BudgetConfig."""
    return BudgetConfig(
        max_briefing_display_count=plan.max_briefing_display,
        max_chat_requests_per_day=plan.max_chat_per_day,
        max_tokens_per_chat_request=plan.max_tokens_per_chat,
        max_daily_collection_jobs=plan.max_daily_collection,
        max_daily_briefing_generations=plan.max_daily_briefing_gen,
        max_daily_expensive_llm_calls=plan.max_daily_expensive_llm,
        daily_budget_usd=plan.daily_budget_usd,
        monthly_budget_usd=plan.monthly_budget_usd,
    )


def get_plan(name: str = "free_beta") -> PlanLimits:
    """Look up a plan by name.  Only free_beta is available."""
    plans = {"free_beta": FREE_BETA}
    return plans.get(name, FREE_BETA)

"""Deterministic clarification profiles for genuinely broad onboarding terms.

The profiles only select from the existing information-type and routing
taxonomy. They never make network/LLM calls or add a second profile model.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from src.sources.information_types import options_for_categories


AMBIGUOUS_INTEREST_PROFILES: List[Dict[str, object]] = [
    {
        "id": "ai",
        "aliases": {"ai", "\uc778\uacf5\uc9c0\ub2a5", "artificial intelligence"},
        "categories": ("AI_TREND",),
        "type_ids": (
            "ai_industry_news", "ai_product_updates", "research_papers", "ai_career_education",
        ),
    },
    {
        "id": "marketing",
        "aliases": {"marketing", "\ub9c8\ucf00\ud305"},
        "categories": ("CONTENT_SNS", "DOMESTIC_INDUSTRY", "CAREER"),
        "type_ids": (
            "marketing_campaign_cases", "marketing_technology", "market_consumer_trends", "career_preparation",
        ),
    },
    {
        "id": "data",
        "aliases": {"data", "\ub370\uc774\ud130"},
        "categories": ("DEVELOPER_TECH", "DOMESTIC_INDUSTRY", "CAREER"),
        "type_ids": (
            "data_analysis", "data_engineering", "data_industry_news", "career_preparation",
        ),
    },
]


def _normalise(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def clarification_for_interest(keyword: object) -> Optional[Dict[str, object]]:
    """Return one optional clarification only for an exact broad term.

    Specific phrases such as ``AI \uc624\ud508\uc18c\uc2a4`` or ``\ub370\uc774\ud130 \uc5d4\uc9c0\ub2c8\uc5b4\ub9c1`` deliberately skip the extra step.
    """
    normalized = _normalise(keyword)
    for profile in AMBIGUOUS_INTEREST_PROFILES:
        aliases = {_normalise(alias) for alias in profile["aliases"]}
        if normalized not in aliases:
            continue
        choices = {
            option["id"]: option
            for option in options_for_categories(profile["categories"])
        }
        return {
            "id": profile["id"],
            "needed": True,
            "options": [dict(choices[type_id]) for type_id in profile["type_ids"] if type_id in choices],
        }
    return None

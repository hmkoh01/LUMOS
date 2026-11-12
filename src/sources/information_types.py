"""Stable reader-facing information-type choices for onboarding and routing."""
from __future__ import annotations

from typing import Dict, Iterable, List, Set


INFORMATION_TYPE_OPTIONS: Dict[str, List[Dict[str, str]]] = {
    "AI_TREND": [
        {"id": "ai_industry_news", "label": "AI \uc0b0\uc5c5 \ub274\uc2a4", "category": "AI_TREND"},
        {"id": "ai_product_updates", "label": "\uc81c\ud488\u00b7\ubaa8\ub378 \ubc1c\ud45c", "category": "AI_TREND"},
        {"id": "ai_open_source", "label": "\uc624\ud508\uc18c\uc2a4", "category": "AI_OPEN_SOURCE"},
        {"id": "research_papers", "label": "\uc5f0\uad6c\ub17c\ubb38", "category": "RESEARCH"},
        {"id": "ai_career_education", "label": "AI \ucde8\uc5c5\u00b7\uad50\uc721", "category": "CAREER"},
    ],
    "AI_OPEN_SOURCE": [
        {"id": "ai_open_source", "label": "\uc624\ud508\uc18c\uc2a4", "category": "AI_OPEN_SOURCE"},
        {"id": "developer_tools", "label": "\uac1c\ubc1c \ub3c4\uad6c", "category": "DEVELOPER_TECH"},
    ],
    "RESEARCH": [{"id": "research_papers", "label": "\uc5f0\uad6c\ub17c\ubb38", "category": "RESEARCH"}],
    "CAREER": [
        {"id": "junior_jobs", "label": "\uc2e0\uc785 \ucc44\uc6a9", "category": "CAREER"},
        {"id": "internships", "label": "\uc778\ud134", "category": "CAREER"},
        {"id": "recruiting_events", "label": "\ucc44\uc6a9\ud589\uc0ac", "category": "CAREER"},
        {"id": "career_preparation", "label": "\ucee4\ub9ac\uc5b4 \uc900\ube44", "category": "CAREER"},
    ],
    "ECONOMY_FINANCE": [
        {"id": "economic_news", "label": "\uacbd\uc81c \ub274\uc2a4", "category": "ECONOMY_FINANCE"},
        {"id": "rates_prices", "label": "\uae08\ub9ac\u00b7\ubb3c\uac00", "category": "ECONOMY_FINANCE"},
        {"id": "industry_companies", "label": "\uae30\uc5c5\u00b7\uc0b0\uc5c5", "category": "ECONOMY_FINANCE"},
        {"id": "financial_markets", "label": "\uae08\uc735\uc2dc\uc7a5", "category": "ECONOMY_FINANCE"},
    ],
    "STARTUP_PROGRAM": [
        {"id": "startup_support", "label": "\uc9c0\uc6d0\uc0ac\uc5c5", "category": "STARTUP_PROGRAM"},
        {"id": "startup_policy", "label": "\ucc3d\uc5c5 \uc815\ucc45", "category": "STARTUP_PROGRAM"},
        {"id": "technology_startup_support", "label": "\uae30\uc220\ucc3d\uc5c5 \uc9c0\uc6d0", "category": "STARTUP_PROGRAM"},
        {"id": "small_business_support", "label": "\uc18c\uc0c1\uacf5\uc778 \uc9c0\uc6d0", "category": "STARTUP_PROGRAM"},
        {"id": "digital_commerce_support", "label": "\ub514\uc9c0\ud138\ucee4\uba38\uc2a4 \uc9c0\uc6d0", "category": "STARTUP_PROGRAM"},
        {"id": "online_market_access", "label": "\uc628\ub77c\uc778 \ud310\ub9e4\u00b7\ud310\ub85c \uc9c0\uc6d0", "category": "STARTUP_PROGRAM"},
    ],
    "STARTUP_PRODUCT": [{"id": "startup_investing", "label": "\ud22c\uc790\u00b7\uc2a4\ud0c0\ud2b8\uc5c5 \ub3d9\ud5a5", "category": "STARTUP_PRODUCT"}],
    "YOUTH_POLICY": [
        {"id": "youth_housing", "label": "\uc8fc\uac70", "category": "YOUTH_POLICY"},
        {"id": "youth_employment", "label": "\ucde8\uc5c5 \uc9c0\uc6d0", "category": "YOUTH_POLICY"},
        {"id": "youth_welfare", "label": "\ubcf5\uc9c0", "category": "YOUTH_POLICY"},
        {"id": "youth_education", "label": "\uad50\uc721", "category": "YOUTH_POLICY"},
    ],
    "CULTURE_TRAVEL_EVENT": [
        {"id": "performances_exhibitions", "label": "\uacf5\uc5f0\u00b7\uc804\uc2dc", "category": "CULTURE_TRAVEL_EVENT"},
        {"id": "local_events", "label": "\uc9c0\uc5ed\ud589\uc0ac", "category": "CULTURE_TRAVEL_EVENT"},
        {"id": "festivals", "label": "\ucd95\uc81c", "category": "CULTURE_TRAVEL_EVENT"},
        {"id": "culture_news", "label": "\ubb38\ud654 \ub274\uc2a4", "category": "CULTURE_TRAVEL_EVENT"},
    ],
    # These categories already participate in the Source Router. Defining
    # reader-facing choices here refines to its existing categories instead
    # of creating a parallel onboarding-profile taxonomy.
    "CONTENT_SNS": [
        # These are intentionally narrower than the legacy CONTENT_SNS
        # bucket.  No broad community/SNS collector may claim them until a
        # matching, operational marketing source is approved.
        {"id": "marketing_campaign_cases", "label": "\ube0c\ub79c\ub4dc\u00b7\ucea0\ud398\uc778 \uc0ac\ub840", "category": "MARKETING_CAMPAIGNS"},
        {"id": "marketing_technology", "label": "\ub514\uc9c0\ud138 \uad11\uace0\u00b7\ub9c8\ucf00\ud305 \uae30\uc220", "category": "MARKETING_TECH"},
    ],
    "DOMESTIC_INDUSTRY": [
        {"id": "market_consumer_trends", "label": "\uc18c\ube44\uc790\u00b7\uc2dc\uc7a5 \ud2b8\ub80c\ub4dc", "category": "MARKET_CONSUMER_TRENDS"},
        {"id": "data_industry_news", "label": "\ub370\uc774\ud130 \uc0b0\uc5c5 \ub3d9\ud5a5", "category": "DATA_INDUSTRY"},
    ],
    "DEVELOPER_TECH": [
        {"id": "data_analysis", "label": "\ub370\uc774\ud130 \ubd84\uc11d", "category": "DEVELOPER_TECH"},
        {"id": "data_engineering", "label": "\ub370\uc774\ud130 \uc5d4\uc9c0\ub2c8\uc5b4\ub9c1", "category": "DEVELOPER_TECH"},
    ],
}

_BY_ID = {item["id"]: item for options in INFORMATION_TYPE_OPTIONS.values() for item in options}


def options_for_categories(categories: Iterable[str]) -> List[Dict[str, str]]:
    seen: Set[str] = set()
    options: List[Dict[str, str]] = []
    for category in categories:
        for item in INFORMATION_TYPE_OPTIONS.get(str(category), []):
            if item["id"] not in seen:
                options.append(dict(item))
                seen.add(item["id"])
    return options


def valid_type_ids(type_ids: Iterable[object]) -> List[str]:
    seen: Set[str] = set()
    valid: List[str] = []
    for type_id in type_ids or []:
        value = str(type_id).strip()
        if value in _BY_ID and value not in seen:
            valid.append(value)
            seen.add(value)
    return valid


def categories_for_type_ids(type_ids: Iterable[object]) -> Set[str]:
    return {item["category"] for type_id in valid_type_ids(type_ids) if (item := _BY_ID.get(type_id))}


def labels_for_type_ids(type_ids: Iterable[object]) -> List[str]:
    return [_BY_ID[type_id]["label"] for type_id in valid_type_ids(type_ids)]


def options_for_type_ids(type_ids: Iterable[object]) -> List[Dict[str, str]]:
    """Return existing reader-facing options without inferring new types."""
    return [dict(_BY_ID[type_id]) for type_id in valid_type_ids(type_ids)]

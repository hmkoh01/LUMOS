from collections import Counter
from dataclasses import asdict
from datetime import date
from typing import Any, Dict, List

from src.sources.source_registry import SOURCE_REGISTRY, source_availability
from src.sources.information_types import categories_for_type_ids


ROUTING_RULES = {
    # Product/news intent is distinct from implementation discovery. Do not
    # make a recently-updated repository the default answer to "AI trend".
    "AI_TREND": ["official_ai_blogs", "company_newsroom", "rss"],
    "AI_OPEN_SOURCE": ["github", "rss"],
    "AI_LLM_AGENT": ["official_ai_blogs", "company_newsroom", "rss"],  # legacy category
    "STARTUP_PRODUCT": ["producthunt", "hackernews", "reddit", "rss"],
    "STARTUP_PROGRAM": ["mss_support_program", "mss_bizinfo", "msit_announcements", "msit_business_rss", "rss"],
    "DEVELOPER_TECH": ["github", "hackernews", "rss", "reddit"],
    # Hacker News is a technology community, not a substitute for a reader's
    # broad content/SNS or marketing request. Keep this category honest until
    # a reviewed source with the requested content rights is operational.
    "CONTENT_SNS": ["youtube", "reddit", "rss"],
    "DOMESTIC_INDUSTRY": ["naver_news", "company_newsroom", "rss"],
    # Crossref resolves/enriches DOI metadata after discovery; it is not an
    # automatic research-discovery route.
    "RESEARCH": ["openalex", "arxiv"],
    # OpenDART is deliberately available only through company tracking, not
    # as a substitute for general economy news or investment guidance.
    "COMPANY_TRACKING": ["opendart", "company_newsroom", "naver_news", "github", "rss"],
    "CAREER": ["public_institution_jobs", "public_service_jobs", "employment24", "msit_recruitment_rss", "rss", "youtube"],
    "ECONOMY_FINANCE": ["opendart", "rss"],
    "YOUTH_POLICY": ["youthcenter_policy", "rss"],
    "CULTURE_TRAVEL_EVENT": ["seoul_culture_events", "kopis", "tourapi", "rss", "youtube"],
    "INDUSTRY_POLICY": ["msit_announcements", "company_newsroom", "rss", "naver_news"],
    "SEMICONDUCTOR_INDUSTRY": ["company_newsroom", "naver_news", "rss", "msit_announcements"],
    "SECURITY_PRIVACY": ["kisa_press", "kisa_research", "rss", "github", "hackernews"],
}


# A route must carry the information type the reader asked for, not merely a
# shared keyword. Source capabilities are checked against this policy before
# priority ranking.
ROUTE_INFORMATION_TYPES = {
    "AI_TREND": {"official_update", "industry_news", "news", "press_release"},
    "AI_OPEN_SOURCE": {"open_source", "repository"},
    "AI_LLM_AGENT": {"official_update", "industry_news", "news"},
    "DEVELOPER_TECH": {"open_source", "repository", "technology", "official_update", "news"},
    "RESEARCH": {"research"},
    "SEMICONDUCTOR_INDUSTRY": {"industry_news", "official_update", "news", "press_release", "government_policy"},
    "CAREER": {"career", "job"},
    "STARTUP_PROGRAM": {"startup_program", "government_rnd_announcement"},
    "YOUTH_POLICY": {"youth_policy"},
    "ECONOMY_FINANCE": {"finance", "disclosure", "economic_policy"},
    "CULTURE_TRAVEL_EVENT": {"tourism", "event", "culture_event"},
    "INDUSTRY_POLICY": {"government_policy", "official_update", "industry_news", "news"},
    "STARTUP_PRODUCT": {"product_launch", "community", "news"},
    "CONTENT_SNS": {"video", "creator", "community", "news"},
    "COMPANY_TRACKING": {"official_update", "industry_news", "news", "repository", "disclosure"},
    "DOMESTIC_INDUSTRY": {"industry_news", "official_update", "news"},
    "SECURITY_PRIVACY": {"official_announcement", "research_report", "news", "technology"},
}


# Exact intent phrases take precedence over broad "AI" or "industry" keyword
# matches. Unicode escapes keep this portable across Windows terminals.
INTENT_PHRASES = {
    "AI_OPEN_SOURCE": ("ai open source", "open-source ai", "ai \uc624\ud508\uc18c\uc2a4", "\uc624\ud508\uc18c\uc2a4 ai", "github ai"),
    "AI_TREND": ("ai trend", "ai trends", "ai industry", "artificial intelligence trend", "ai \ud2b8\ub80c\ub4dc", "\uc778\uacf5\uc9c0\ub2a5 \ud2b8\ub80c\ub4dc", "ai \uc0b0\uc5c5 \ub3d9\ud5a5"),
    "RESEARCH": ("llm research", "llm paper", "large language model research", "\uc5d8\ub7f4\uc5e0 \ub17c\ubb38", "llm \uc5f0\uad6c\ub17c\ubb38", "\uc778\uacf5\uc9c0\ub2a5 \ub17c\ubb38"),
    "SEMICONDUCTOR_INDUSTRY": ("semiconductor industry", "semiconductor trend", "\ubc18\ub3c4\uccb4 \uc0b0\uc5c5 \ub3d9\ud5a5", "\ubc18\ub3c4\uccb4 \ub3d9\ud5a5"),
    "CAREER": (
        "new graduate hiring", "junior developer hiring",
        "\uc2e0\uc785 \uac1c\ubc1c\uc790 \ucc44\uc6a9", "\ucde8\uc5c5 \ucc44\uc6a9",
        # Broad career wording must win over the incidental "developer"
        # token; otherwise a first-time job seeker is sent to GitHub/HN.
        "\ucde8\uc5c5", "\uc778\ud134", "\uc2e0\uc785 \uac1c\ubc1c\uc790",
    ),
    "STARTUP_PROGRAM": ("startup support program", "startup grant", "\uc2a4\ud0c0\ud2b8\uc5c5 \uc9c0\uc6d0\uc0ac\uc5c5", "\ucc3d\uc5c5 \uc9c0\uc6d0\uc0ac\uc5c5"),
    "YOUTH_POLICY": ("youth housing", "\uccad\ub144 \uc8fc\uac70\uc9c0\uc6d0", "\uccad\ub144\uc815\ucc45"),
    "ECONOMY_FINANCE": ("interest rate policy", "economic policy", "\uae08\ub9ac \uc815\ucc45", "\uacbd\uc81c \uae08\uc735"),
    "CULTURE_TRAVEL_EVENT": ("local cultural event", "regional festival", "\uc9c0\uc5ed \ubb38\ud654\ud589\uc0ac", "\uc9c0\uc5ed \ucd95\uc81c"),
}


KEYWORD_CATEGORY_HINTS = {
    "AI_LLM_AGENT": ["ai", "llm", "agent", "assistant", "automation", "생성형", "인공지능"],
    "STARTUP_PRODUCT": ["startup", "product", "saas", "launch", "growth", "스타트업", "제품"],
    "DEVELOPER_TECH": ["developer", "github", "api", "open source", "python", "machine learning", "개발", "오픈소스"],
    "CONTENT_SNS": ["youtube", "content", "creator", "sns", "콘텐츠", "크리에이터", "마케팅", "마케터", "marketing"],
    "DOMESTIC_INDUSTRY": ["naver", "korea", "domestic", "industry", "국내", "산업"],
    "RESEARCH": ["research", "paper", "arxiv", "논문", "연구"],
    "COMPANY_TRACKING": ["company", "newsroom", "hyundai", "samsung", "기업", "현대차"],
    "CAREER": ["career", "job", "hiring", "커리어", "채용"],
    "SECURITY_PRIVACY": ["security", "privacy", "cyber", "정보보안", "개인정보", "사이버"],
    "STARTUP_PROGRAM": ["support program", "grant", "funding", "startup support", "\ucc3d\uc5c5", "\uc9c0\uc6d0\uc0ac\uc5c5", "\uacf5\uace0"],
    "ECONOMY_FINANCE": ["finance", "financial", "stock", "market", "interest rate", "monetary policy", "\uae08\uc735", "\uc8fc\uc2dd", "\uacbd\uc81c", "\uacf5\uc2dc"],
    "YOUTH_POLICY": ["youth", "youth policy", "youth benefit", "\uccad\ub144", "\uc815\ucc45", "\uccad\ub144\uc815\ucc45"],
    "CULTURE_TRAVEL_EVENT": ["travel", "tour", "festival", "exhibition", "event", "\uc5ec\ud589", "\ucd95\uc81c", "\uc804\uc2dc", "\ud589\uc0ac", "\ubb38\ud654"],
    "INDUSTRY_POLICY": ["industry policy", "regulation", "government policy", "\uc0b0\uc5c5", "\uaddc\uc81c", "\uc0b0\uc5c5\uc815\ucc45"],
}


# Broad hints are only consulted when an interest did not match one of the
# specific phrases above.
KEYWORD_CATEGORY_HINTS["AI_TREND"] = ["ai", "llm", "agent", "assistant", "automation", "artificial intelligence", "\uc778\uacf5\uc9c0\ub2a5"]
KEYWORD_CATEGORY_HINTS["SEMICONDUCTOR_INDUSTRY"] = ["semiconductor", "chip", "\ubc18\ub3c4\uccb4"]


class SourceRouter:
    def plan(
        self,
        profile: Dict[str, Any],
        settings: Dict[str, Any],
        connectors: List[Dict[str, Any]],
        interests: List[Dict[str, Any]],
        feedback_events: List[Dict[str, Any]] = None,
        source_configs: List[Dict[str, Any]] = None,
        max_sources: int = 5,
    ) -> List[Dict[str, Any]]:
        categories = self.classify_interests(profile, interests)
        config_map = {item["source_id"]: item for item in source_configs or []}
        def selection_mode(source_id: str) -> str:
            config = config_map.get(source_id, {})
            return config.get("selection_mode") or ("enabled" if config.get("enabled") else "disabled")

        available_sources = {
            source_id for source_id in SOURCE_REGISTRY
            if source_availability(source_id, config_map.get(source_id, {}).get("config_json", {}))["available"]
        }
        automatic_sources = {source_id for source_id in available_sources if selection_mode(source_id) == "auto"}
        forced_sources = {source_id for source_id in available_sources if selection_mode(source_id) == "enabled"}
        region_preference = settings.get("source_region_preference", "both")
        source_scores: Dict[str, Dict[str, Any]] = {}

        for category, category_score in categories.items():
            for index, source_id in enumerate(ROUTING_RULES.get(category, [])):
                if source_id not in SOURCE_REGISTRY or source_id not in automatic_sources:
                    continue
                metadata = SOURCE_REGISTRY[source_id]
                source_config = config_map.get(source_id, {})
                config_json = source_config.get("config_json", {})
                if category in set(config_json.get("excluded_for", [])):
                    continue
                source_types = set(source_availability(source_id, config_json)["capabilities"].get("information_types", []))
                expected_types = ROUTE_INFORMATION_TYPES.get(category, set())
                if expected_types and not source_types.intersection(expected_types):
                    continue
                config_priority = int(source_config.get("priority", 50)) / 100
                base_priority = category_score + (len(ROUTING_RULES[category]) - index) * 0.05
                if category in set(config_json.get("preferred_for", [])):
                    base_priority += 0.25
                regions = source_availability(source_id, config_json)["capabilities"].get("regions", [])
                if region_preference == "domestic" and "domestic" in regions:
                    base_priority += 0.15
                elif region_preference == "international" and "international" in regions:
                    base_priority += 0.15
                if source_id not in source_scores:
                    source_scores[source_id] = {
                        "source": source_id,
                        "category": category,
                        "reason": "",
                        "priority": config_priority,
                        "collection_limit": metadata.default_limit,
                        "metadata": asdict(metadata),
                        "source_config": source_config.get("config_json", {}),
                        "information_types": sorted(source_types.intersection(expected_types) or source_types),
                    }
                source_scores[source_id]["priority"] += base_priority
                if base_priority >= source_scores[source_id].get("_best_score", 0):
                    source_scores[source_id]["category"] = category
                    source_scores[source_id]["_best_score"] = base_priority

        # No type-compatible approved source is an honest "waiting" state.
        # Never fill it with GitHub/HN merely to make a route non-empty.

        for source_id in forced_sources:
            if source_id in source_scores:
                source_scores[source_id]["priority"] += 100
                continue
            metadata = SOURCE_REGISTRY[source_id]
            source_config = config_map.get(source_id, {})
            source_scores[source_id] = {
                "source": source_id,
                "category": metadata.categories[0] if metadata.categories else "DEVELOPER_TECH",
                "reason": "",
                "manually_selected": True,
                "priority": 100 + int(source_config.get("priority", 50)) / 100,
                "collection_limit": metadata.default_limit,
                "metadata": asdict(metadata),
                "source_config": source_config.get("config_json", {}),
            }
        # A direct choice must not silently disappear merely because more than
        # ``max_sources`` sources were also recommended automatically.
        planned = sorted(source_scores.values(), key=lambda item: item["priority"], reverse=True)[
            : max(max_sources, len(forced_sources))
        ]
        primary_terms = self._top_interest_terms(interests, profile)
        for item in planned:
            metadata = SOURCE_REGISTRY[item["source"]]
            if not item["reason"]:
                if item.pop("manually_selected", False):
                    item["reason"] = (
                        "Selected directly by the user; queries follow interests including "
                        f"{', '.join(primary_terms[:3]) or 'general product signals'}; {metadata.description}"
                    )
                else:
                    item["reason"] = (
                        f"Selected for {item['category']} because interests include "
                        f"{', '.join(primary_terms[:3]) or 'general product signals'}; {metadata.description}"
                    )
            item["route_date"] = date.today().isoformat()
            item.pop("_best_score", None)
        return planned

    def classify_interests(self, profile: Dict[str, Any], interests: List[Dict[str, Any]]) -> Dict[str, float]:
        scores = Counter()
        text_parts = []
        text_parts.append(str(profile.get("role") or ""))
        text_parts.append(str(profile.get("role_detail") or ""))
        text_parts.extend(str(goal) for goal in profile.get("goals_json") or [])
        raw_onboarding = profile.get("raw_onboarding_json") or profile.get("raw_onboarding") or {}
        type_preferences = raw_onboarding.get("interest_type_preferences", {}) if isinstance(raw_onboarding, dict) else {}
        # Legacy profiles only have display labels in interest_types_json. A
        # structured preference is deliberately handled per interest below so
        # its selected type does not leak into every other interest.
        structured_preferences_configured = isinstance(raw_onboarding, dict) and bool(
            raw_onboarding.get("information_type_preferences_configured")
        )
        if not type_preferences and not structured_preferences_configured:
            text_parts.extend(str(kind) for kind in profile.get("interest_types_json") or [])
        normalized_preferences = {
            str(keyword).casefold(): value
            for keyword, value in type_preferences.items()
            if isinstance(value, list)
        }
        for interest in interests:
            if interest.get("status", "active") != "active":
                continue
            keyword = str(interest.get("keyword") or "")
            selected_categories = categories_for_type_ids(normalized_preferences.get(keyword.casefold(), []))
            for category in selected_categories:
                # A reader's explicit type choice is more precise than a broad
                # keyword hint, while still allowing the interest itself to
                # contribute its normal routing category.
                scores[category] += 5
            if selected_categories:
                # An explicit type is a constraint for this interest, not an
                # invitation to also collect every broad keyword match.
                continue
            explicit_categories = self._explicit_intent_categories(keyword)
            if explicit_categories:
                for category in explicit_categories:
                    scores[category] += 5
                # Specific reader intent wins over generic terms such as "AI".
                continue
            text_parts.append(keyword)
            text_parts.append(str(interest.get("category") or ""))

        haystack = " ".join(text_parts).lower()
        for category, hints in KEYWORD_CATEGORY_HINTS.items():
            for hint in hints:
                if hint.lower() in haystack:
                    scores[category] += 1

        if not scores:
            # An unrecognised interest must remain unsupported until there is a
            # matching source profile.  Treating it as developer technology
            # silently sent unrelated people to GitHub/Hacker News.
            return {}
        max_score = max(scores.values())
        return {category: score / max_score for category, score in scores.items()}

    @staticmethod
    def _explicit_intent_categories(text: str) -> List[str]:
        normalized = " ".join(str(text or "").casefold().split())
        return [
            category for category, phrases in INTENT_PHRASES.items()
            if any(phrase.casefold() in normalized for phrase in phrases)
        ]

    def _top_interest_terms(self, interests: List[Dict[str, Any]], profile: Dict[str, Any]) -> List[str]:
        terms = [item.get("keyword", "") for item in interests if item.get("keyword")]
        if not terms:
            terms.extend(profile.get("interest_types_json") or [])
        if not terms and profile.get("role"):
            terms.append(profile["role"])
        return terms

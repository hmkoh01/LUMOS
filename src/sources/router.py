from collections import Counter
from dataclasses import asdict
from datetime import date
from typing import Any, Dict, List

from src.sources.source_registry import SOURCE_REGISTRY


ROUTING_RULES = {
    "AI_LLM_AGENT": ["official_ai_blogs", "github", "hackernews", "reddit", "arxiv"],
    "STARTUP_PRODUCT": ["producthunt", "hackernews", "reddit", "rss"],
    "DEVELOPER_TECH": ["github", "hackernews", "rss", "reddit"],
    "CONTENT_SNS": ["youtube", "reddit", "rss", "hackernews"],
    "DOMESTIC_INDUSTRY": ["naver_news", "company_newsroom", "rss"],
    "RESEARCH": ["arxiv", "github", "official_ai_blogs"],
    "COMPANY_TRACKING": ["company_newsroom", "naver_news", "github", "rss"],
    "CAREER": ["naver_news", "rss", "reddit", "youtube"],
}


KEYWORD_CATEGORY_HINTS = {
    "AI_LLM_AGENT": ["ai", "llm", "agent", "assistant", "automation", "생성형", "인공지능"],
    "STARTUP_PRODUCT": ["startup", "product", "saas", "launch", "growth", "스타트업", "제품"],
    "DEVELOPER_TECH": ["developer", "github", "api", "open source", "python", "개발", "오픈소스"],
    "CONTENT_SNS": ["youtube", "content", "creator", "sns", "콘텐츠", "크리에이터", "마케팅", "마케터", "marketing"],
    "DOMESTIC_INDUSTRY": ["naver", "korea", "domestic", "industry", "국내", "산업"],
    "RESEARCH": ["research", "paper", "arxiv", "논문", "연구"],
    "COMPANY_TRACKING": ["company", "newsroom", "hyundai", "samsung", "기업", "현대차"],
    "CAREER": ["career", "job", "hiring", "커리어", "채용"],
}


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
        enabled_sources = {
            source_id
            for source_id, metadata in SOURCE_REGISTRY.items()
            if bool(config_map.get(source_id, {}).get("enabled", metadata.enabled_by_default))
        }
        legacy_enabled = set(settings.get("enabled_sources_json") or [])
        if legacy_enabled:
            enabled_sources = enabled_sources.intersection(legacy_enabled).union(
                source_id for source_id in enabled_sources if source_id in config_map
            )
        source_scores: Dict[str, Dict[str, Any]] = {}

        for category, category_score in categories.items():
            for index, source_id in enumerate(ROUTING_RULES.get(category, [])):
                if source_id not in SOURCE_REGISTRY or source_id not in enabled_sources:
                    continue
                metadata = SOURCE_REGISTRY[source_id]
                source_config = config_map.get(source_id, {})
                config_priority = int(source_config.get("priority", 50)) / 100
                base_priority = category_score + (len(ROUTING_RULES[category]) - index) * 0.05
                if source_id not in source_scores:
                    source_scores[source_id] = {
                        "source": source_id,
                        "category": category,
                        "reason": "",
                        "priority": config_priority,
                        "collection_limit": metadata.default_limit,
                        "metadata": asdict(metadata),
                        "source_config": source_config.get("config_json", {}),
                    }
                source_scores[source_id]["priority"] += base_priority
                if base_priority >= source_scores[source_id].get("_best_score", 0):
                    source_scores[source_id]["category"] = category
                    source_scores[source_id]["_best_score"] = base_priority

        if not source_scores:
            for source_id in ["hackernews", "github", "rss"]:
                if source_id not in enabled_sources:
                    continue
                metadata = SOURCE_REGISTRY[source_id]
                source_config = config_map.get(source_id, {})
                source_scores[source_id] = {
                    "source": source_id,
                    "category": "DEVELOPER_TECH",
                    "reason": "Default route because no strong interest category was detected.",
                    "priority": metadata.trust_score,
                    "collection_limit": metadata.default_limit,
                    "metadata": asdict(metadata),
                    "source_config": source_config.get("config_json", {}),
                }

        planned = sorted(source_scores.values(), key=lambda item: item["priority"], reverse=True)[:max_sources]
        primary_terms = self._top_interest_terms(interests, profile)
        for item in planned:
            metadata = SOURCE_REGISTRY[item["source"]]
            if not item["reason"]:
                item["reason"] = (
                    f"Selected for {item['category']} because interests include "
                    f"{', '.join(primary_terms[:3]) or 'general product signals'}; {metadata.description}"
                )
            item["route_date"] = date.today().isoformat()
            item.pop("_best_score", None)
        return planned

    def classify_interests(self, profile: Dict[str, Any], interests: List[Dict[str, Any]]) -> Dict[str, float]:
        text_parts = []
        text_parts.append(str(profile.get("role") or ""))
        text_parts.append(str(profile.get("role_detail") or ""))
        text_parts.extend(str(goal) for goal in profile.get("goals_json") or [])
        text_parts.extend(str(kind) for kind in profile.get("interest_types_json") or [])
        for interest in interests:
            if interest.get("status", "active") != "active":
                continue
            text_parts.append(str(interest.get("keyword") or ""))
            text_parts.append(str(interest.get("category") or ""))

        haystack = " ".join(text_parts).lower()
        scores = Counter()
        for category, hints in KEYWORD_CATEGORY_HINTS.items():
            for hint in hints:
                if hint.lower() in haystack:
                    scores[category] += 1

        if not scores:
            scores["DEVELOPER_TECH"] = 1
        max_score = max(scores.values())
        return {category: score / max_score for category, score in scores.items()}

    def _top_interest_terms(self, interests: List[Dict[str, Any]], profile: Dict[str, Any]) -> List[str]:
        terms = [item.get("keyword", "") for item in interests if item.get("keyword")]
        if not terms:
            terms.extend(profile.get("interest_types_json") or [])
        if not terms and profile.get("role"):
            terms.append(profile["role"])
        return terms

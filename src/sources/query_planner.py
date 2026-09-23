from typing import Any, Dict, List
from src.context.interest_matching import interest_terms


class QueryPlanner:
    def build_queries(
        self,
        routes: List[Dict[str, Any]],
        profile: Dict[str, Any],
        interests: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        keywords = self._keywords(profile, interests)
        role = profile.get("role") or ""
        goals = profile.get("goals_json") or []
        planned = []
        for route in routes:
            source = route["source"]
            source_config = route.get("source_config") or {}
            config_keywords = source_config.get("keywords") or []
            effective_keywords = self._unique([*config_keywords, *keywords])
            queries = self._queries_for_source(source, effective_keywords, role, goals, route["category"], source_config)
            planned.append({**route, "queries": queries})
        return planned

    def _keywords(self, profile: Dict[str, Any], interests: List[Dict[str, Any]]) -> List[str]:
        active_interests = [item for item in interests if item.get("status", "active") == "active"]
        active_interests = sorted(active_interests, key=lambda item: float(item.get("weight", 0)), reverse=True)
        keywords = [item["keyword"] for item in active_interests if item.get("keyword")]
        result = []
        for keyword in keywords:
            keyword = str(keyword).strip()
            if keyword and keyword not in result:
                result.append(keyword)
        return result[:8]

    def _queries_for_source(
        self,
        source: str,
        keywords: List[str],
        role: str,
        goals: List[str],
        category: str,
        source_config: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:
        source_config = source_config or {}
        feed_urls = source_config.get("feed_urls") or []
        base_params = {
            "language": source_config.get("language"),
            "region": source_config.get("region"),
        }
        base_params = {key: value for key, value in base_params.items() if value}
        groups = [interest_terms(keyword) for keyword in keywords]
        preferred = [next((term for term in group if not self._contains_korean(term)), group[0]) for group in groups if group]
        keywords = self._unique([*preferred, *[term for group in groups for term in group]])
        english = [kw for kw in keywords if not self._contains_korean(kw)]
        korean = [kw for kw in keywords if self._contains_korean(kw)]
        primary = english or keywords
        korean_primary = korean or ["생성형 AI", "스타트업", "커리어"]

        if source == "github":
            terms = primary[:4]
            min_stars = int(source_config.get("min_stars", 20))
            sort = source_config.get("sort", "updated")
            return [
                {"query": term, "params": {**base_params, "sort": sort, "min_stars": min_stars}}
                for term in self._unique(terms)[:4]
            ]
        if source == "hackernews":
            story_kind = source_config.get("story_type") or source_config.get("story_kind", "topstories")
            max_story_scan = int(source_config.get("max_story_scan", 100))
            return [
                {"query": term, "params": {**base_params, "search": True, "story_type": story_kind, "max_story_scan": max_story_scan}}
                for term in self._unique(primary)[:8]
            ]
        if source == "producthunt":
            terms = primary[:3] + ["productivity", "AI assistant", "research automation"]
            return [{"query": term, "params": {"kind": "launch"}} for term in self._unique(terms)[:4]]
        if source == "naver_news":
            return [{"query": term, "params": {"locale": "ko-KR"}} for term in self._unique(korean_primary[:4])[:4]]
        if source == "reddit":
            return [{"query": f"{term} community reaction", "params": {"kind": "discussion"}} for term in self._unique(primary[:3])[:3]]
        if source == "youtube":
            return [{"query": f"{term} trend", "params": {"kind": "video"}} for term in self._unique(primary[:3])[:3]]
        if source in {"rss", "official_ai_blogs", "company_newsroom"}:
            terms = primary[:3] + [category.replace("_", " ").lower()]
            params = {**base_params, "kind": "feed_filter", "feed_urls": feed_urls, "keywords": primary[:5]}
            if feed_urls:
                return [{"query": url, "params": params} for url in feed_urls[:4]]
            return [{"query": term, "params": params} for term in self._unique(terms)[:4]]
        if source == "arxiv":
            terms = primary[:3] + ["agents", "retrieval augmented generation"]
            return [{"query": term, "params": {"kind": "paper"}} for term in self._unique(terms)[:4]]
        if source == "official_ai_blogs":
            terms = primary[:3] + ["model release", "agent platform"]
            return [{"query": term, "params": {"kind": "official_update"}} for term in self._unique(terms)[:4]]
        return [{"query": term, "params": {}} for term in primary[:3]]

    def _contains_korean(self, text: str) -> bool:
        return any("가" <= char <= "힣" for char in text)

    def _unique(self, values: List[str]) -> List[str]:
        result = []
        for value in values:
            value = str(value).strip()
            if value and value not in result:
                result.append(value)
        return result

from typing import Any, Dict, List
from src.context.interest_matching import interest_terms, youtube_search_profiles
from src.sources.domestic_collection_strategy import public_job_discovery_plans, support_program_collection_plan


class QueryPlanner:
    def build_queries(
        self,
        routes: List[Dict[str, Any]],
        profile: Dict[str, Any],
        interests: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        interest_keywords = self._keywords(profile, interests)
        role = profile.get("role") or ""
        goals = profile.get("goals_json") or []
        planned = []
        for route in routes:
            source = route["source"]
            source_config = route.get("source_config") or {}
            config_keywords = source_config.get("keywords") or []
            effective_keywords = self._unique([*interest_keywords, *config_keywords])
            queries = self._queries_for_source(
                source, effective_keywords, role, goals, route["category"], source_config,
                interest_keywords=interest_keywords,
            )
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
        interest_keywords: List[str] = None,
    ) -> List[Dict[str, Any]]:
        source_config = source_config or {}
        interest_keywords = self._unique(interest_keywords or keywords)
        feed_urls = source_config.get("feed_urls") or []
        base_params = {
            "language": source_config.get("language"),
            "region": source_config.get("region"),
            "source_region": source_config.get("source_region"),
            "content_region": source_config.get("content_region"),
            "content_type": source_config.get("content_type"),
            "usage_status": source_config.get("usage_status"),
            "content_policy": source_config.get("content_policy"),
            "opportunity_only": source_config.get("opportunity_only"),
        }
        base_params = {key: value for key, value in base_params.items() if value}
        original_keywords = self._unique(keywords)
        # Domestic opportunity APIs use documented provider filters and
        # metadata matching, not translated free-text expansion.  Handle them
        # before ``interest_terms`` so planning is fully offline and cannot
        # turn a user interest into an unrelated external translation request.
        if source == "public_institution_jobs":
            plans = public_job_discovery_plans(
                original_keywords,
                information_types=source_config.get("information_types") or source_config.get("requested_information_types") or [],
                # Code values can only be supplied by a previously loaded,
                # versioned official code definition; user text never becomes
                # a code-valued query parameter here.
                code_filters=source_config.get("official_code_filters") or {},
                codebook_verified=bool(source_config.get("official_codebook_version")),
            )
            return [
                {"query": plan.profile_id, "params": {**base_params, **plan.params, "collection_scope": plan.shared_scope,
                    "direct_evidence_terms": list(plan.direct_evidence_terms), "requires_codebook": list(plan.requires_codebook),
                    "requires_developer_role_evidence": plan.profile_id in {"junior_developer", "it_software"}}}
                for plan in plans
            ]
        if source == "mss_support_program":
            year = source_config.get("sprtBizYr")
            if not year:
                # The collector itself blocks calls without the only mandatory
                # documented filter.  Avoid emitting generic keyword requests.
                return []
            plan = support_program_collection_plan(year=year)
            return [{"query": plan.profile_id, "params": {**base_params, **plan.params, "collection_scope": plan.shared_scope}}]
        interest_groups = [interest_terms(keyword) for keyword in interest_keywords]
        interest_bilingual_terms = self._unique(
            [*interest_keywords, *[term for group in interest_groups for term in group]]
        )
        groups = [interest_terms(keyword) for keyword in original_keywords]
        preferred = [next((term for term in group if not self._contains_korean(term)), group[0]) for group in groups if group]
        keywords = self._unique([*preferred, *[term for group in groups for term in group]])
        english = [kw for kw in keywords if not self._contains_korean(kw)]
        korean = [kw for kw in keywords if self._contains_korean(kw)]
        # Give every saved interest one search slot before spending slots on
        # aliases of the highest-weight interest. The old flattened English
        # list could fill a source's query cap with marketing/marketer/etc.
        # and leave other interests completely unsearched.
        primary = self._unique([*preferred, *english, *korean]) or keywords
        korean_primary = korean or ["생성형 AI", "스타트업", "커리어"]
        bilingual_terms = self._unique([*original_keywords, *[term for group in groups for term in group]])

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
            semantic_queries = []
            for keyword in original_keywords:
                for profile in youtube_search_profiles(keyword):
                    semantic_queries.append({
                        "query": profile["query"],
                        "params": {
                            **base_params,
                            # Search each language in its own language instead
                            # of forcing Korean interests through an English-only
                            # result set (or vice versa).
                            "language": "ko" if self._contains_korean(profile["query"]) else "en",
                            "kind": "video",
                            "semantic_excludes": profile["exclude"],
                            "interest_keyword": profile["interest"],
                        },
                    })
            if semantic_queries:
                unique_queries = []
                seen_queries = set()
                for entry in semantic_queries:
                    query_key = entry["query"].casefold()
                    if query_key not in seen_queries:
                        unique_queries.append(entry)
                        seen_queries.add(query_key)
                return unique_queries[:2]
            return [{"query": f"{term} trend", "params": {**base_params, "kind": "video"}} for term in self._unique(primary[:2])[:2]]
        if source in {
            "rss", "official_ai_blogs", "company_newsroom", "geeknews", "kisa_press", "kisa_research",
            "msit_business_rss", "msit_recruitment_rss",
        }:
            terms = primary[:3] + [category.replace("_", " ").lower()]
            # One configured feed is fetched only once. Its Korean and English
            # entries are matched against the same bilingual interest set.
            params = {
                **base_params, "kind": "feed_filter", "feed_urls": feed_urls,
                # Configuration keywords may guide a collector but never count
                # as proof that an item matches the user's saved interest.
                "keywords": interest_bilingual_terms[:10],
                "source_role": source_config.get("source_role", "primary"),
                "verification_status": source_config.get("verification_status", "unverified"),
                "content_filter": source_config.get("content_filter"),
                "rights_evidence_url": source_config.get("rights_evidence_url"),
                "requires_post_rights": bool(source_config.get("requires_post_rights")),
            }
            if feed_urls:
                return [{"query": url, "params": params} for url in feed_urls[:4]]
            return [{"query": term, "params": params} for term in self._unique(terms)[:4]]
        if source == "arxiv":
            terms = primary[:3] + ["agents", "retrieval augmented generation"]
            return [{"query": term, "params": {"kind": "paper"}} for term in self._unique(terms)[:4]]
        if source == "crossref":
            # Crossref is a metadata discovery source, not a full-text index.
            # Keep one carefully chosen topical query per user interest rather
            # than expanding aliases until generic words such as "research" or
            # "paper" dominate the request.
            return [self._crossref_query(keyword, base_params) for keyword in original_keywords[:4]]
        if source == "openalex":
            # Collect a single, shared monthly candidate pool. Engine v2
            # independently applies daily/weekly/monthly publication windows
            # after dedupe, so period-specific searches only repeated the same
            # provider request and spent three budget slots per interest.
            return [self._openalex_query(keyword, {**base_params, "briefing_period": "monthly", "collection_scope": "monthly_shared"})
                    for keyword in original_keywords[:1]]
        if source == "mss_bizinfo":
            return [
                {"query": term, "params": {**base_params, "kind": "startup_program"}}
                for term in self._unique(primary)[:4]
            ]
        if source == "msit_announcements":
            return [
                {"query": term, "params": {**base_params, "kind": "government_rnd_announcement"}}
                for term in self._unique(primary)[:4]
            ]
        if source == "official_ai_blogs":
            terms = primary[:3] + ["model release", "agent platform"]
            return [{"query": term, "params": {"kind": "official_update"}} for term in self._unique(terms)[:4]]
        return [{"query": term, "params": {}} for term in primary[:3]]

    def _contains_korean(self, text: str) -> bool:
        return any("가" <= char <= "힣" for char in text)

    def _crossref_query(self, keyword: str, base_params: Dict[str, Any]) -> Dict[str, Any]:
        raw_interest = str(keyword).strip()
        normalized = raw_interest.casefold()
        params = {
            **base_params,
            "kind": "research_metadata",
            "raw_interest": raw_interest,
            "crossref_search_field": "query.title",
        }
        # "Foundation model" is deliberately not added to an LLM query: it is
        # a wider concept and would create false positives.  It can be searched
        # when a user actually saved that interest.
        if "llm" in normalized or "large language model" in normalized:
            return {
                "query": "Large Language Model",
                "params": {
                    **params,
                    "crossref_topic": "llm",
                    "accepted_title_terms": [
                        "llm", "large language model", "generative language model",
                    ],
                },
            }
        return {"query": raw_interest, "params": params}

    def _openalex_query(self, keyword: str, base_params: Dict[str, Any]) -> Dict[str, Any]:
        raw_interest = str(keyword).strip()
        normalized = raw_interest.casefold()
        query = "Large Language Model" if "llm" in normalized or "large language model" in normalized else raw_interest
        return {"query": query, "params": {**base_params, "kind": "research_metadata", "raw_interest": raw_interest}}

    def _unique(self, values: List[str]) -> List[str]:
        result = []
        for value in values:
            value = str(value).strip()
            if value and value not in result:
                result.append(value)
        return result

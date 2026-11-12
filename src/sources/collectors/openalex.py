"""Small, metadata-only OpenAlex discovery collector.

OpenAlex is used only for research discovery.  It requests five work records
at most, never downloads PDFs or abstracts, and treats API update metadata as
audit information rather than publication recency.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from src.context.interest_matching import matches_interest
from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery, build_source_item_id


class OpenAlexCollector(BaseCollector):
    source_id = "openalex"
    ENDPOINT = "https://api.openalex.org/works"
    # A monthly shared pool must survive relevance filtering before it feeds
    # three independent periods. This is still one bounded metadata request.
    MAX_RESULTS = 20
    RECENCY_WINDOW_DAYS = 365
    CACHE_TTL_SECONDS = 15 * 60
    _cache: Dict[str, tuple[float, Dict[str, Any], Dict[str, str]]] = {}

    def __init__(self, fetch_json: Optional[Callable[[str, float, Dict[str, str]], Any]] = None, timeout: float = 8.0):
        self.fetch_json = fetch_json or self._fetch_json
        self.timeout = timeout

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        # One bounded list request is enough for a shared collection job.
        query = next((entry for entry in queries if str(entry.query).strip()), SourceQuery(source=self.source_id, query=""))
        search = str(query.query or "").strip()
        if not search:
            return CollectorResult(source=self.source_id, errors=["OpenAlex query must not be empty; no request was made."], items=[])
        bounded_limit = max(1, min(int(limit or 1), self.MAX_RESULTS))
        url = self._url(search, bounded_limit, query.params or {})
        try:
            payload, response_headers = self._cached_or_fetch(url)
        except Exception as exc:
            return CollectorResult(source=self.source_id, errors=[f"network request failed: {exc}"], items=[])

        items, seen = [], set()
        for record in (payload or {}).get("results") or []:
            item = self._normalise(record, query)
            if not item or item.source_item_id in seen:
                continue
            seen.add(item.source_item_id)
            items.append(item)
            if len(items) >= bounded_limit:
                break
        warnings = []
        if (payload or {}).get("meta", {}).get("cost_usd") is not None:
            warnings.append(f"openalex_cost_usd={payload['meta']['cost_usd']}")
        remaining = response_headers.get("x-ratelimit-remaining")
        reset = response_headers.get("x-ratelimit-reset")
        if remaining is not None:
            warnings.append(f"openalex_rate_limit_remaining={remaining}")
        if reset is not None:
            warnings.append(f"openalex_rate_limit_reset_seconds={reset}")
        return CollectorResult(source=self.source_id, items=items, warnings=warnings)

    def _url(self, search: str, limit: int, query_params: Optional[Dict[str, Any]] = None) -> str:
        # Search titles, abstracts, and OpenAlex keywords rather than the
        # broader full-text index.  The response still projects metadata only:
        # this controls matching, not what LUMOS stores.  Relevance must be
        # first: sorting only by a date turns a topical search into a list of
        # whichever recently-dated records happen to contain the words.
        # ``updated_date`` is intentionally not used for sorting or filtering
        # recency.
        period = str((query_params or {}).get("briefing_period") or "monthly").lower()
        period_days = {"daily": 1, "weekly": 7, "monthly": 30}
        reference = str((query_params or {}).get("reference_date") or "")[:10]
        try:
            today = datetime.strptime(reference, "%Y-%m-%d").date() if reference else self._today_kst()
        except ValueError:
            today = self._today_kst()
        earliest = (today - timedelta(days=period_days.get(period, self.RECENCY_WINDOW_DAYS) - 1)).isoformat()
        params = {
            "search.title_abstract_keywords": search,
            "filter": f"from_publication_date:{earliest},type:article",
            "sort": "relevance_score:desc,publication_date:desc",
            "per-page": max(1, min(limit, self.MAX_RESULTS)),
            "select": "id,title,doi,publication_date,updated_date,authorships,primary_location,topics,type",
        }
        return f"{self.ENDPOINT}?{urllib.parse.urlencode(params)}"

    @staticmethod
    def _today_kst() -> date:
        from src.engine.evaluation.periods import KOREA_TZ
        return datetime.now(KOREA_TZ).date()

    def _cached_or_fetch(self, url: str) -> tuple[Dict[str, Any], Dict[str, str]]:
        now = time.monotonic()
        cached = self._cache.get(url)
        if cached and now - cached[0] < self.CACHE_TTL_SECONDS:
            return cached[1], cached[2]
        headers = {"Accept": "application/json", "User-Agent": "LUMOS/0.1"}
        # The free OpenAlex key identifies the account whose $1/day free
        # credit is used. Keep it out of the URL, logs and persisted items.
        api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        received = self.fetch_json(url, self.timeout, headers)
        payload, headers = received if isinstance(received, tuple) else (received, {})
        self._cache[url] = (now, payload, headers)
        return payload, headers

    def _normalise(self, record: Dict[str, Any], query: SourceQuery) -> Optional[CollectedItem]:
        title = str(record.get("title") or "").strip()
        publication_date = self._date(record.get("publication_date"))
        if not title or not publication_date or publication_date[:10] > date.today().isoformat():
            return None
        interest = str((query.params or {}).get("raw_interest") or query.query or "").strip()
        if interest and not self._matches_interest(title, interest):
            return None
        doi = str(record.get("doi") or "").strip()
        primary_location = record.get("primary_location") or {}
        landing_url = str(primary_location.get("landing_page_url") or "").strip()
        url = doi if doi.startswith("https://doi.org/") else landing_url
        if not url:
            return None
        openalex_id = str(record.get("id") or "").strip()
        identifier = openalex_id or build_source_item_id(self.source_id, url, title, publication_date)
        authors = [str((entry.get("author") or {}).get("display_name") or "").strip() for entry in record.get("authorships") or []]
        topics = [str((entry.get("topic") or {}).get("display_name") or "").strip() for entry in record.get("topics") or []]
        updated = self._date(record.get("updated_date"))
        research_role = "reference_review" if self._is_review_title(title) else "research_update"
        return CollectedItem(
            source=self.source_id, source_item_id=identifier, url=url, title=title[:300], summary="",
            author=", ".join(author for author in authors[:5] if author)[:120], published_at=publication_date,
            metrics_json={
                "content_kind": "research_metadata", "doi": doi or None,
                "publication_date": publication_date, "metadata_updated_at": updated,
                "publication_date_precision": "day", "topics": [topic for topic in topics[:5] if topic],
                "work_type": record.get("type"), "research_role": research_role,
            },
            raw_json={
                "openalex_id": openalex_id, "doi": doi or None, "landing_page_url": landing_url or None,
                "publication_date": publication_date, "metadata_updated_at": updated,
                "publication_date_precision": "day", "research_role": research_role,
                "preserve_missing_published_at": True, "fulltext_collected": False,
            }, route_id=query.route_id,
        )

    @staticmethod
    def _date(value: Any) -> Optional[str]:
        if not value:
            return None
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").isoformat()
        except ValueError:
            return None

    @staticmethod
    def _matches_interest(title: str, interest: str) -> bool:
        normalized = str(interest or "").casefold()
        title_normalized = str(title or "").casefold()
        if "llm" in normalized or "large language model" in normalized:
            return any(term in title_normalized for term in ("llm", "large language model", "generative language model"))
        return matches_interest(title, interest)

    @staticmethod
    def _is_review_title(title: str) -> bool:
        return bool(re.search(r"\b(?:survey|review|overview)\b", title or "", re.I))

    @staticmethod
    def _fetch_json(url: str, timeout: float, headers: Dict[str, str]) -> tuple[Dict[str, Any], Dict[str, str]]:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))
            budget_headers = {
                key.lower(): value for key, value in response.headers.items()
                if key.lower() in {"x-ratelimit-remaining", "x-ratelimit-reset"}
            }
            return payload, budget_headers

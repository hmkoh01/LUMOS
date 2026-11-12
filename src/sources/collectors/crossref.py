"""Crossref bibliographic metadata collector (metadata only, never full text)."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery


class CrossrefCollector(BaseCollector):
    source_id = "crossref"
    # Pin the documented REST API version instead of depending on the
    # unversioned compatibility route.
    BASE_URL = "https://api.crossref.org/v1/works"
    # The polite-pool list-request limit is currently 3/s. Use a deliberately
    # lower process-wide ceiling and a short response cache so concurrent
    # workers cannot amplify the same query.
    CACHE_TTL_SECONDS = 900.0
    MIN_REQUEST_INTERVAL_SECONDS = 1.0
    _cache: Dict[str, tuple[float, Any]] = {}
    _request_lock = threading.Lock()
    _last_request_at = 0.0
    DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)

    def __init__(self, fetch_json: Optional[Callable[[str, float, Dict[str, str]], Any]] = None, timeout: float = 8.0):
        self.fetch_json = fetch_json or self._fetch_json
        self.timeout = timeout

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        items, errors, seen = [], [], set()
        mailto = os.environ.get("CROSSREF_MAILTO", "").strip()
        for query in queries:
            if len(items) >= limit:
                break
            try:
                payload = self._fetch_cached(
                    self._url(query.query, min(limit - len(items), 20), mailto, query.params), mailto
                )
            except Exception as exc:
                errors.append(f"search {query.query}: {exc}")
                continue
            for record in (payload or {}).get("message", {}).get("items", []):
                item = self._normalise(record, query)
                if item and item.source_item_id not in seen and self._matches(item, query):
                    seen.add(item.source_item_id)
                    items.append(item)
                if len(items) >= limit:
                    break
        return CollectorResult(source=self.source_id, items=items, errors=errors)

    def _fetch_cached(self, url: str, mailto: str) -> Any:
        now = time.monotonic()
        with self._request_lock:
            cached = self._cache.get(url)
            if cached and now - cached[0] < self.CACHE_TTL_SECONDS:
                return cached[1]
            delay = self.MIN_REQUEST_INTERVAL_SECONDS - (now - type(self)._last_request_at)
            if delay > 0:
                time.sleep(delay)
            type(self)._last_request_at = time.monotonic()
            payload = self.fetch_json(url, self.timeout, self._headers(mailto))
            self._cache[url] = (time.monotonic(), payload)
            return payload

    def _url(self, query: str, rows: int, mailto: str, query_params: Optional[Dict[str, Any]] = None) -> str:
        """Build a topical-discovery request without falling back to all works.

        ``query.bibliographic`` is intended for resolving a known citation.  A
        LUMOS interest is instead a discovery query, so use Crossref's
        title-scoped search.  We deliberately do not sort by ``published``:
        that made malformed future publication metadata outrank relevant work.
        Crossref's relevance ranking is the useful first-pass ordering here;
        LUMOS still applies its own publication-date and relevance checks.
        """
        term = " ".join(str(query or "").split())
        if not term:
            raise ValueError("Crossref discovery query must not be empty")
        requested_field = str((query_params or {}).get("crossref_search_field") or "query.title")
        if requested_field not in {"query.title", "query"}:
            raise ValueError("Unsupported Crossref search field")
        # A server-side upper publication bound avoids known bad future dates
        # before they consume the small response budget.  The normalizer keeps
        # the equivalent client-side guard for cached/fixture responses.
        today = datetime.now(timezone.utc).date().isoformat()
        params = {
            requested_field: term,
            "rows": min(20, max(1, int(rows))),
            "filter": f"until-pub-date:{today}",
        }
        if mailto:
            params["mailto"] = mailto
        return f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"

    @staticmethod
    def _headers(mailto: str) -> Dict[str, str]:
        agent = "LUMOS/0.1"
        if mailto:
            agent += f" (mailto:{mailto})"
        return {"Accept": "application/json", "User-Agent": agent}

    def _normalise(self, record: Dict[str, Any], query: SourceQuery) -> Optional[CollectedItem]:
        doi = str(record.get("DOI") or "").strip()
        title = " ".join(record.get("title") or []).strip()
        # A non-empty string alone is not a reliable citation identifier.  We
        # do not resolve it here (that would be another external request), but
        # require the standard DOI shape before publishing its doi.org link.
        if not doi or not self.DOI_PATTERN.match(doi) or not title:
            return None
        published_print = self._date_metadata(record.get("published-print"))
        published_online = self._date_metadata(record.get("published-online"))
        issued = self._date_metadata(record.get("issued"))
        # Indexing and deposit timestamps describe Crossref processing, never
        # the research publication date. Keep them for audit only.
        created = self._date_metadata(record.get("created"))
        indexed = self._date_metadata(record.get("indexed"))
        publication_dates = [
            ("published_online", published_online),
            ("published_print", published_print),
            ("issued", issued),
        ]
        # Only a complete year-month-day can participate in recency.  For a
        # fully dated record choose the earliest public publication evidence,
        # so a later print issue never makes an older online paper look new.
        reliable_dates = [(source, data["value"]) for source, data in publication_dates if data["value"]]
        publication_source, published = min(reliable_dates, key=lambda entry: entry[1]) if reliable_dates else (None, None)
        if published and datetime.fromisoformat(published).astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(days=1):
            # Deposited future dates occur in Crossref metadata. They are not
            # evidence of a future research publication and must not enter a
            # recommendation feed.
            return None
        authors = record.get("author") or []
        author = ", ".join(" ".join(filter(None, (entry.get("given"), entry.get("family")))) for entry in authors[:3])
        return CollectedItem(
            source=self.source_id, source_item_id=doi.lower(), url=f"https://doi.org/{doi}", title=title[:300],
            # Crossref says bibliographic metadata is broadly reusable, but an
            # abstract can remain copyrighted by its publisher or author. The
            # collector is deliberately metadata-only: Gemini never receives
            # an abstract merely because it appeared in this response.
            summary="", author=author, published_at=published,
            metrics_json={
                "content_kind": "research_metadata", "citation_count": int(record.get("is-referenced-by-count") or 0),
                "published_print_at": published_print["value"], "published_print_precision": published_print["precision"],
                "published_online_at": published_online["value"], "published_online_precision": published_online["precision"],
                "issued_at": issued["value"], "issued_precision": issued["precision"],
                "publication_date_source": publication_source, "publication_date_precision": "day" if published else "unknown",
                "metadata_created_at": created["value"], "metadata_created_precision": created["precision"],
                "metadata_indexed_at": indexed["value"], "metadata_indexed_precision": indexed["precision"],
            },
            raw_json={
                "doi": doi, "type": record.get("type"), "publisher": record.get("publisher"), "crossref_query": query.query,
                "published_print_at": published_print, "published_online_at": published_online,
                "issued_at": issued, "metadata_created_at": created, "metadata_indexed_at": indexed,
                "publication_date_source": publication_source,
                # A year/month-only Crossref value is bibliographically useful
                # but not evidence that the work is newly published.  Preserve
                # the missing value through CollectedItem.to_dict().
                "preserve_missing_published_at": published is None,
            },
            route_id=query.route_id,
        )

    @staticmethod
    def _matches(item: CollectedItem, query: SourceQuery) -> bool:
        interest = str((query.params or {}).get("raw_interest") or query.query or "").strip()
        if not interest:
            return True
        title = item.title.casefold()
        accepted_title_terms = (query.params or {}).get("accepted_title_terms") or []
        if accepted_title_terms:
            return any(str(term).casefold() in title for term in accepted_title_terms)
        # LLM is a high-signal acronym; a generic research query otherwise
        # admits papers which only match "research" or "paper".
        if "llm" in interest.casefold() or "large language model" in interest.casefold():
            return any(term in title for term in ("llm", "large language model", "generative language model"))
        from src.context.interest_matching import matches_interest
        return matches_interest(title, interest)

    @staticmethod
    def _date_metadata(value: Any) -> Dict[str, Optional[str]]:
        parts = (value or {}).get("date-parts", [[]])
        values = parts[0] if parts else []
        if not values:
            return {"value": None, "precision": "unknown", "raw": None}
        precision = {1: "year", 2: "month", 3: "day"}.get(len(values), "unknown")
        raw = "-".join(str(part) for part in values[:3])
        if len(values) < 3:
            return {"value": None, "precision": precision, "raw": raw}
        try:
            year, month, day = values[:3]
            return {
                "value": datetime(int(year), int(month), int(day), tzinfo=timezone.utc).isoformat(),
                "precision": "day", "raw": raw,
            }
        except (TypeError, ValueError):
            return {"value": None, "precision": "invalid", "raw": raw}

    @staticmethod
    def _fetch_json(url: str, timeout: float, headers: Dict[str, str]):
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))

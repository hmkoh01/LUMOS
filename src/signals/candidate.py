from typing import Any, Dict, List
from urllib.parse import urlsplit

from src.storage.sqlite_store import SQLiteStore
from src.context.interest_matching import matches_interest
from src.signals.identity import article_key
from src.signals.commercial_filter import commercial_page_reason


def is_youtube_short(item: Dict[str, Any]) -> bool:
    """Catch Shorts that arrive through a non-YouTube collector (e.g. HN)."""
    url = str(item.get("url") or item.get("source_url") or "")
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host, path = parts.hostname or "", parts.path.casefold()
    return host.casefold().endswith("youtube.com") and path.startswith("/shorts/")


class CandidateBuilder:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def create_from_source_items(
        self,
        source_items: List[Dict[str, Any]],
        interests: List[Dict[str, Any]],
        pipeline_run_id: int = None,
    ) -> List[Dict[str, Any]]:
        created = []
        keywords = [item["keyword"] for item in interests if item.get("keyword") and item.get("status", "active") == "active"]
        seen = set()
        for item in source_items:
            # YouTube's own collector filters duration and #shorts already,
            # but a Shorts URL can also be discovered by HN/RSS.
            if is_youtube_short(item):
                continue
            # Do not turn sales, subscription, or checkout pages into a daily
            # signal, even when their SEO text matches a saved interest.
            if commercial_page_reason(item):
                continue
            matched = self.match_keywords(item, keywords)
            identity = article_key(item)
            if not matched or identity in seen:
                continue
            seen.add(identity)
            candidate_id = self.store.create_signal_candidate(
                source_item_id=item["id"],
                route_id=item.get("route_id") or 0,
                matched_keywords=matched,
                pipeline_run_id=pipeline_run_id,
                category=item.get("route_category") or item.get("category") or "",
            )
            candidate = self.store.get_candidate(candidate_id)
            if candidate:
                created.append(candidate)
        return created

    def match_keywords(self, item: Dict[str, Any], keywords: List[str]) -> List[str]:
        raw = item.get("raw_json") or {}
        search_text = raw.get("search_text", "")
        tags = " ".join(str(tag) for tag in raw.get("tags") or [])
        # YouTube creators often keep the exact subject in tags rather than the title.
        haystack = f"{item.get('title', '')} {item.get('summary', '')} {tags} {search_text}".lower()
        matched = []
        for keyword in keywords:
            keyword_text = str(keyword).strip()
            if keyword_text and matches_interest(haystack, keyword_text):
                matched.append(keyword_text)
        return matched

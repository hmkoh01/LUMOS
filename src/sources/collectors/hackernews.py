import json
import urllib.request
from datetime import datetime
import time
from typing import Any, Callable, Dict, List, Optional

from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery


class HackerNewsCollector(BaseCollector):
    source_id = "hackernews"
    BASE_URL = "https://hacker-news.firebaseio.com/v0"

    def __init__(self, fetch_json: Optional[Callable[[str, float], Any]] = None, timeout: float = 5.0):
        self.fetch_json = fetch_json or self._fetch_json
        self.timeout = timeout

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        warnings = []
        try:
            story_kind = self._story_kind(queries)
            story_ids = self.fetch_json(f"{self.BASE_URL}/{story_kind}.json", self.timeout) or []
        except Exception as exc:
            return CollectorResult(source=self.source_id, errors=[f"story list: {exc}"], items=[])

        query_terms = [query.query.lower() for query in queries if query.query]
        route_id = queries[0].route_id if queries else None
        max_scan = self._max_story_scan(queries, limit)
        items: List[CollectedItem] = []
        fallback: List[CollectedItem] = []
        for story_id in story_ids[:max_scan]:
            try:
                story = self.fetch_json(f"{self.BASE_URL}/item/{story_id}.json", self.timeout)
            except Exception as exc:
                warnings.append(f"item {story_id}: {exc}")
                continue
            item = self._normalize_story(story or {}, route_id)
            if not item:
                continue
            haystack = f"{item.title} {item.url} {item.summary}".lower()
            if query_terms and any(term in haystack for term in query_terms):
                items.append(item)
            else:
                fallback.append(item)
            if len(items) >= limit:
                break

        if len(items) < limit:
            items.extend(fallback[: limit - len(items)])
        return CollectorResult(source=self.source_id, items=items[:limit], warnings=warnings)

    def _story_kind(self, queries: List[SourceQuery]) -> str:
        for query in queries:
            params = query.params or {}
            kind = params.get("story_type") or params.get("kind")
            if kind in {"topstories", "newstories", "beststories"}:
                return kind
        return "topstories"

    def _max_story_scan(self, queries: List[SourceQuery], limit: int) -> int:
        for query in queries:
            try:
                return max(limit, min(500, int((query.params or {}).get("max_story_scan", max(25, limit * 8)))))
            except Exception:
                pass
        return max(25, limit * 8)

    def _normalize_story(self, story: Dict[str, Any], route_id: Optional[int]) -> Optional[CollectedItem]:
        if not story or story.get("type") not in {None, "story"}:
            return None
        story_id = str(story.get("id") or "")
        title = story.get("title") or ""
        if not story_id or not title:
            return None
        url = story.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
        published_at = datetime.utcfromtimestamp(int(story.get("time") or 0)).isoformat() if story.get("time") else None
        comments = int(story.get("descendants") or 0)
        score = int(story.get("score") or 0)
        return CollectedItem(
            source=self.source_id,
            source_item_id=story_id,
            url=url,
            title=title[:300],
            summary=(story.get("text") or "")[:500],
            author=story.get("by") or "",
            published_at=published_at,
            metrics_json={"score": score, "comments": comments, "descendants": comments},
            raw_json={
                "hn_id": story_id,
                "type": story.get("type"),
                "score": score,
                "descendants": comments,
                "url_present": bool(story.get("url")),
            },
            route_id=route_id,
        )

    def _fetch_json(self, url: str, timeout: float):
        request = urllib.request.Request(url, headers={"User-Agent": "LUMOS/0.1"})
        last_exc = None
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))
            except Exception as exc:
                last_exc = exc
                if attempt == 0:
                    time.sleep(0.2)
        raise last_exc

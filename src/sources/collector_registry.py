from typing import Dict, List, Optional

from src.sources.collectors.base import BaseCollector, CollectorResult, NoOpCollector, SourceQuery
from src.sources.collectors.github import GitHubCollector
from src.sources.collectors.hackernews import HackerNewsCollector
from src.sources.collectors.mock import MockCollector
from src.sources.collectors.rss import RSSCollector


RSS_BACKED_SOURCES = {"rss", "official_ai_blogs", "company_newsroom"}
IMPLEMENTED_SOURCES = {"mock", "hackernews", "github", *RSS_BACKED_SOURCES}
PLACEHOLDER_SOURCES = {
    "producthunt",
    "reddit",
    "youtube",
    "naver_news",
    "arxiv",
}

COLLECTOR_OVERRIDES: Dict[str, BaseCollector] = {}


class CollectorRegistry:
    def __init__(self, overrides: Optional[Dict[str, BaseCollector]] = None):
        self.overrides = overrides or COLLECTOR_OVERRIDES

    def get(self, source_id: str, mode: str = "mock") -> BaseCollector:
        mode = self.normalize_mode(mode)
        if source_id in self.overrides:
            return self.overrides[source_id]
        if mode == "mock":
            return MockCollector()
        if source_id in RSS_BACKED_SOURCES:
            return RSSCollector(source_id=source_id)
        if source_id == "hackernews":
            return HackerNewsCollector()
        if source_id == "github":
            return GitHubCollector()
        if mode == "hybrid":
            return MockCollector()
        return NoOpCollector(source_id)

    def collect(self, source_id: str, queries: List[SourceQuery], limit: int, mode: str = "mock") -> CollectorResult:
        collector = self.get(source_id, mode=mode)
        if isinstance(collector, MockCollector):
            return collector.collect(queries, limit=limit)
        return collector.collect(queries, limit=limit)

    def support_status(self, source_id: str, mode: str = "mock") -> str:
        if source_id in self.overrides:
            return "implemented"
        if self.normalize_mode(mode) == "mock":
            return "mock"
        if source_id in IMPLEMENTED_SOURCES:
            return "implemented"
        if source_id in PLACEHOLDER_SOURCES:
            return "placeholder"
        return "unknown"

    def normalize_mode(self, mode: str) -> str:
        if mode not in {"mock", "hybrid", "live"}:
            return "mock"
        return mode

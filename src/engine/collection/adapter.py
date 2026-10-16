"""Adapter: convert v1 CollectedItem → v2 RawCandidate.

The existing source collectors (GitHub, HackerNews, RSS, YouTube) produce
``CollectedItem`` objects.  The v2 engine evaluates ``RawCandidate`` objects.

This thin adapter allows engine v2 to reuse all existing collectors without
duplicating fetch/parse logic.
"""

from __future__ import annotations

from typing import List

from src.engine.models import RawCandidate
from src.sources.collectors.base import CollectedItem


def collected_item_to_candidate(item: CollectedItem) -> RawCandidate:
    """Convert a v1 CollectedItem to a v2 RawCandidate."""
    d = item.to_dict()
    return RawCandidate(
        dedupe_key=d.get("dedupe_key", ""),
        source=d.get("source", ""),
        url=d.get("url", ""),
        title=d.get("title", ""),
        summary=d.get("summary", ""),
        author=d.get("author", ""),
        published_at=d.get("published_at"),
        metrics=d.get("metrics_json", {}),
        collected_at=d.get("collected_at"),
    )


def batch_convert(items: List[CollectedItem]) -> List[RawCandidate]:
    """Convert a list of v1 CollectedItems to v2 RawCandidates."""
    return [collected_item_to_candidate(item) for item in items]

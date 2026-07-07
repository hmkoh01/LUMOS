from datetime import datetime
from typing import Any, Dict, List

from src.sources.source_registry import SOURCE_REGISTRY
from src.storage.sqlite_store import SQLiteStore


class RankingService:
    WEIGHTS = {
        "relevance_score": 0.40,
        "recency_score": 0.20,
        "source_trust_score": 0.15,
        "community_score": 0.15,
        "novelty_score": 0.10,
    }

    def __init__(self, store: SQLiteStore):
        self.store = store

    def rank(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        recent_titles = [signal["title"].lower() for signal in self.store.get_recent_signals(limit=50)]
        ranked = []
        for candidate in candidates:
            breakdown = self.score_breakdown(candidate, recent_titles)
            final_score = sum(breakdown[key] * weight for key, weight in self.WEIGHTS.items())
            final_score = round(final_score, 4)
            self.store.update_signal_candidate_score(candidate["id"], final_score, breakdown)
            candidate["score"] = final_score
            candidate["score_breakdown_json"] = breakdown
            candidate["status"] = "ranked"
            ranked.append(candidate)
        return sorted(ranked, key=lambda item: item["score"], reverse=True)

    def score_breakdown(self, candidate: Dict[str, Any], recent_titles: List[str]) -> Dict[str, float]:
        matched = candidate.get("matched_keywords_json") or []
        relevance = min(1.0, 0.25 + 0.25 * len(matched)) if matched else 0.25
        recency = self._recency_score(candidate.get("published_at") or candidate.get("collected_at"))
        source = candidate.get("source")
        metadata = SOURCE_REGISTRY.get(source)
        trust = metadata.trust_score if metadata else 0.5
        community = self._community_score(source, candidate.get("metrics_json") or {})
        novelty = self._novelty_score(candidate.get("title", ""), recent_titles)
        return {
            "relevance_score": round(relevance, 4),
            "recency_score": round(recency, 4),
            "source_trust_score": round(trust, 4),
            "community_score": round(community, 4),
            "novelty_score": round(novelty, 4),
        }

    def _recency_score(self, timestamp: str) -> float:
        if not timestamp:
            return 0.5
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return 0.5
        age_hours = max(0.0, (datetime.utcnow() - parsed).total_seconds() / 3600)
        if age_hours <= 24:
            return 1.0
        if age_hours <= 72:
            return 0.7
        return 0.4

    def _community_score(self, source: str, metrics: Dict[str, Any]) -> float:
        if source == "github":
            raw = metrics.get("stars", 0) / 200
        elif source == "hackernews":
            raw = (metrics.get("points", 0) + metrics.get("comments", 0) * 2) / 200
        elif source in {"producthunt", "reddit"}:
            raw = (metrics.get("upvotes", 0) + metrics.get("comments", 0)) / 200
        elif source == "youtube":
            raw = metrics.get("views", 0) / 10000
        else:
            raw = metrics.get("mentions", metrics.get("score", 20)) / 100
        return max(0.0, min(1.0, raw))

    def _novelty_score(self, title: str, recent_titles: List[str]) -> float:
        title_lower = (title or "").lower()
        if not title_lower:
            return 0.5
        for recent in recent_titles:
            if title_lower == recent or title_lower[:40] in recent:
                return 0.2
        return 1.0

from datetime import date
from typing import Any, Dict, List

from src.signals.korean_briefing import build_korean_briefing
from src.storage.sqlite_store import SQLiteStore
from src.signals.identity import article_key


class SignalGenerator:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def generate_from_candidates(
        self,
        ranked_candidates: List[Dict[str, Any]],
        replace_today: bool = True,
        pipeline_run_id: int = None,
        archive_reason: str = None,
    ) -> List[Dict[str, Any]]:
        settings = self.store.get_settings()
        profile = self.store.get_profile() or {}
        interests = self.store.get_interests(limit=50)
        signal_count = max(1, int(settings.get("signal_count", 3)))

        if replace_today:
            self.store.archive_today_signals(reason=archive_reason)

        selected = []
        seen = set()
        for candidate in ranked_candidates:
            identity = article_key(candidate)
            if identity in seen:
                continue
            seen.add(identity)
            selected.append(candidate)
            if len(selected) >= signal_count:
                break
        generated = []
        for rank, candidate in enumerate(selected, start=1):
            signal_id = self.store.create_signal(
                self._build_signal(candidate, profile, interests, rank),
                pipeline_run_id=pipeline_run_id,
            )
            signal = self.store.get_signal(signal_id)
            if signal:
                generated.append(signal)
        return generated

    def _build_signal(
        self,
        candidate: Dict[str, Any],
        profile: Dict[str, Any],
        interests: List[Dict[str, Any]],
        rank: int,
    ) -> Dict[str, Any]:
        matched = candidate.get("matched_keywords_json") or []
        role = profile.get("role") or "your work"
        source = candidate.get("source", "mock")
        category = candidate.get("route_category") or candidate.get("category") or "trend"
        keyword_text = ", ".join(matched[:3]) if matched else "your saved interests"
        title = self._title(candidate)
        summary = self._summary(candidate)
        action = self._action(candidate, matched)
        metadata = build_korean_briefing(
            title=title,
            summary=summary,
            source=source,
            category=category,
            matched_keywords=matched,
            role=role,
            action_hint=action,
        )
        return {
            "signal_date": date.today().isoformat(),
            "title": title,
            "summary": summary,
            "why_it_matters": (
                f"This matters for {role} because it matches {keyword_text} "
                f"and came from {source}, which was selected for {category} monitoring."
            ),
            "category": category,
            "recommended_action": action,
            "source_name": source,
            "source_url": candidate.get("url", ""),
            "source_items_json": [
                {
                    "source_item_id": candidate.get("source_item_id"),
                    "source": source,
                    "title": candidate.get("title"),
                    "summary": candidate.get("summary"),
                    "url": candidate.get("url"),
                    "score": candidate.get("score"),
                    "score_breakdown": candidate.get("score_breakdown_json"),
                }
            ],
            "metadata_json": metadata,
            "confidence": min(0.95, max(0.1, float(candidate.get("score", 0.5)))),
            "rank": rank,
            "status": "active",
        }

    def _title(self, candidate: Dict[str, Any]) -> str:
        return candidate.get("title") or "New signal detected"

    def _summary(self, candidate: Dict[str, Any]) -> str:
        summary = candidate.get("summary") or ""
        return summary[:500]

    def _action(self, candidate: Dict[str, Any], matched: List[str]) -> str:
        if matched:
            return f"Review this through the lens of {matched[0]} and decide whether to keep tracking it."
        return "Review this source item and decide whether it should become a tracked interest."

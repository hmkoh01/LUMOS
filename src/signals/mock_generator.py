from datetime import date
from typing import Any, Dict, List

from src.signals.korean_briefing import build_korean_briefing
from src.storage.sqlite_store import SQLiteStore


class MockSignalGenerator:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def generate_daily_signals(self) -> List[Dict[str, Any]]:
        settings = self.store.get_settings()
        profile = self.store.get_profile() or {}
        interests = self.store.get_interests(limit=50)
        signal_count = max(1, int(settings.get("signal_count", 3)))

        keywords = [item["keyword"] for item in interests if item.get("keyword")]
        if not keywords:
            keywords = self._fallback_keywords(profile)

        created = []
        for rank in range(1, signal_count + 1):
            keyword = keywords[(rank - 1) % len(keywords)]
            signal = self._build_signal(keyword, profile, rank)
            signal_id = self.store.create_signal(signal)
            created.append(self.store.get_signal(signal_id))
        return [signal for signal in created if signal]

    def _fallback_keywords(self, profile: Dict[str, Any]) -> List[str]:
        interest_types = profile.get("interest_types_json") or []
        if interest_types:
            return list(interest_types)
        if profile.get("role"):
            return [profile["role"]]
        return ["AI agent", "productivity tools", "personal research automation"]

    def _build_signal(self, keyword: str, profile: Dict[str, Any], rank: int) -> Dict[str, Any]:
        role = profile.get("role") or "your current work"
        variants = [
            (
                f"{keyword} tools are moving toward proactive workflow automation",
                f"Teams around {keyword} are packaging research, monitoring, and handoff into background workflows instead of manual search loops.",
                "workflow automation",
                f"Pick one recurring {keyword} research task and define what a daily signal should contain.",
            ),
            (
                f"Signal-first UX is becoming more important for {keyword}",
                f"Products are shifting from dashboard-heavy discovery to timely, personalized briefs that reach users before they open an app.",
                "product strategy",
                "Review whether the first user touchpoint should be a push briefing, not a homepage.",
            ),
            (
                f"Early products are testing personalized research automation around {keyword}",
                f"Startups are combining user context, selected external sources, and lightweight ranking to create smaller but more relevant updates.",
                "startup experiments",
                f"Track one adjacent product that mentions {keyword} and compare its signal quality.",
            ),
        ]
        title, summary, category, action = variants[(rank - 1) % len(variants)]
        metadata = build_korean_briefing(
            title=title,
            summary=summary,
            source="mock",
            category=category,
            matched_keywords=[keyword],
            role=role,
            action_hint=action,
        )
        return {
            "signal_date": date.today().isoformat(),
            "title": title,
            "summary": summary,
            "why_it_matters": f"This is relevant because your profile is centered on {role}, and '{keyword}' appears in your interest graph.",
            "category": category,
            "recommended_action": action,
            "source_name": "Mock Source",
            "source_url": "https://example.com/lumos/mock-signal",
            "source_items_json": [{"source": "mock", "keyword": keyword, "title": title, "summary": summary}],
            "metadata_json": metadata,
            "confidence": min(0.95, 0.72 + rank * 0.03),
            "rank": rank,
            "status": "new",
        }

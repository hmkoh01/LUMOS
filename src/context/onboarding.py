from typing import Any, Dict, Iterable, List

from src.storage.schemas import DEFAULT_CONNECTORS
from src.storage.sqlite_store import SQLiteStore


class OnboardingService:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        keywords = self._normalize_terms(data.get("keywords", []))
        interest_types = self._normalize_terms(data.get("interest_types", []))
        goals = self._normalize_terms(data.get("goals", []))

        profile = self.store.upsert_profile(
            {
                "role": data.get("role", ""),
                "role_detail": data.get("role_detail", ""),
                "goals": goals,
                "interest_types": interest_types,
                "raw_onboarding": data,
            }
        )

        settings_update = {"onboarding_completed": True}
        if data.get("preferred_signal_count") is not None:
            settings_update["signal_count"] = data["preferred_signal_count"]
        if data.get("briefing_time"):
            settings_update["briefing_time"] = data["briefing_time"]

        connectors = self._normalize_connectors(data.get("connectors", {}))
        if connectors:
            settings_update["enabled_connectors_json"] = connectors
        settings = self.store.update_settings(settings_update)

        for connector_type, enabled in connectors.items():
            self.store.update_connector(connector_type, enabled)

        seed_terms = []
        seed_terms.extend(keywords)
        seed_terms.extend(interest_types)
        if data.get("role"):
            seed_terms.append(str(data["role"]))

        for index, keyword in enumerate(dict.fromkeys(seed_terms)):
            self.store.upsert_interest(
                keyword=keyword,
                category="onboarding",
                weight=max(0.5, 1.0 - index * 0.03),
                source="onboarding",
                evidence={"goals": goals, "role": data.get("role", "")},
            )

        return {
            "profile": profile,
            "settings": settings,
            "connectors": self.store.get_connectors(),
            "interest_graph": self.store.get_interests(),
        }

    def _normalize_terms(self, values: Any) -> List[str]:
        if isinstance(values, str):
            values = values.replace("\n", ",").split(",")
        if not isinstance(values, Iterable):
            return []
        terms = []
        for value in values:
            term = str(value).strip()
            if term and term not in terms:
                terms.append(term)
        return terms

    def _normalize_connectors(self, connectors: Any) -> Dict[str, bool]:
        if not isinstance(connectors, dict):
            return {}
        return {
            key: bool(connectors.get(key, False))
            for key in DEFAULT_CONNECTORS
            if key in connectors
        }


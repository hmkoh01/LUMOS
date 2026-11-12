from typing import Any, Dict, Iterable, List

from src.storage.schemas import DEFAULT_CONNECTORS
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore
from src.sources.information_types import labels_for_type_ids, valid_type_ids


class OnboardingService:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def save(self, data: Dict[str, Any], user_id: int = DEFAULT_LOCAL_USER_ID) -> Dict[str, Any]:
        keywords = self._normalize_terms(data.get("keywords", []))
        interest_types = self._normalize_terms(data.get("interest_types", []))
        type_preferences = self._normalize_type_preferences(data.get("interest_type_preferences", {}), keywords)
        selected_type_labels = labels_for_type_ids(
            type_id for type_ids in type_preferences.values() for type_id in type_ids
        )
        # Keep the legacy field for profiles created before the optional
        # per-interest choices existed, but prefer labels derived from valid IDs.
        profile_interest_types = selected_type_labels or interest_types
        goals = self._normalize_terms(data.get("goals", []))
        source_hints = self._normalize_terms(data.get("source_hints", []))
        raw_onboarding = dict(data)
        raw_onboarding["interest_type_preferences"] = type_preferences
        # This marker distinguishes a deliberate (possibly empty) optional
        # choice from legacy display labels.  Without it, clearing a choice in
        # the profile screen could silently restore an old broad label during
        # routing.
        raw_onboarding["information_type_preferences_configured"] = True
        raw_onboarding["source_hints"] = source_hints

        profile = self.store.upsert_profile(
            {
                "role": data.get("role", ""),
                "role_detail": data.get("role_detail", ""),
                "goals": goals,
                "interest_types": profile_interest_types,
                "raw_onboarding": raw_onboarding,
            },
            user_id=user_id,
        )

        settings_update = {"onboarding_completed": True}
        if data.get("preferred_signal_count") is not None:
            settings_update["signal_count"] = data["preferred_signal_count"]
        if data.get("briefing_time"):
            settings_update["briefing_time"] = data["briefing_time"]

        connectors = self._normalize_connectors(data.get("connectors", {}))
        if connectors:
            settings_update["enabled_connectors_json"] = connectors
        settings = self.store.update_settings(settings_update, user_id=user_id)

        for connector_type, enabled in connectors.items():
            self.store.update_connector(connector_type, enabled, user_id=user_id)

        seed_terms = []
        seed_terms.extend(keywords)
        # Information-type labels are routing preferences, not independent
        # user interests. Preserve legacy input only when no structured choice
        # was supplied by an older client.
        if not type_preferences:
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
                user_id=user_id,
            )

        return {
            "profile": profile,
            "settings": settings,
            "connectors": self.store.get_connectors(user_id=user_id),
            "interest_graph": self.store.get_interests(user_id=user_id),
        }

    def update_information_type_preferences(
        self, values: Any, user_id: int = DEFAULT_LOCAL_USER_ID
    ) -> Dict[str, Any]:
        """Update only optional per-interest type choices for one user.

        Interests themselves, source hints, goals and settings are deliberately
        preserved.  The existing interest rows are the authority for which
        preference keys are accepted, so another user's or deleted interest
        cannot be introduced through this endpoint.
        """
        profile = self.store.get_profile(user_id=user_id) or {}
        active_interests = self.store.get_interests(
            status="active", limit=None, user_id=user_id
        )
        keywords = [str(item.get("keyword") or "") for item in active_interests]
        type_preferences = self._normalize_type_preferences(values, keywords)
        raw_onboarding = dict(profile.get("raw_onboarding_json") or {})
        raw_onboarding["interest_type_preferences"] = type_preferences
        raw_onboarding["information_type_preferences_configured"] = True
        return self.store.upsert_profile(
            {
                "role": profile.get("role", ""),
                "role_detail": profile.get("role_detail", ""),
                "goals": profile.get("goals_json", []),
                "interest_types": labels_for_type_ids(
                    type_id
                    for type_ids in type_preferences.values()
                    for type_id in type_ids
                ),
                "raw_onboarding": raw_onboarding,
            },
            user_id=user_id,
        )

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

    def _normalize_type_preferences(self, values: Any, keywords: List[str]) -> Dict[str, List[str]]:
        if not isinstance(values, dict):
            return {}
        known_keywords = {keyword.casefold(): keyword for keyword in keywords}
        normalized: Dict[str, List[str]] = {}
        for raw_keyword, raw_type_ids in values.items():
            keyword = known_keywords.get(str(raw_keyword).strip().casefold())
            if not keyword:
                continue
            type_ids = valid_type_ids(raw_type_ids if isinstance(raw_type_ids, list) else [])
            if type_ids:
                normalized[keyword] = type_ids
        return normalized

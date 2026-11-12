from typing import Any, Dict, Iterable, Optional

from src.storage.schemas import FEEDBACK_EVENT_TYPES
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore
from src.sources.information_types import categories_for_type_ids, valid_type_ids


FEEDBACK_REASON_CODES = {
    "ignored": {
        "unrelated_subtopic",
        "too_technical",
        "already_known",
        "not_needed_now",
        "too_general",
    },
    "tracked": {
        "directly_relevant",
        "practical_useful",
        "easy_to_understand",
        "timely",
    },
}


def _safe_values(values: Iterable[object], limit: int = 8) -> list[str]:
    """Keep compact labels only; never persist source body/title as feedback."""
    result: list[str] = []
    for value in values or []:
        text = " ".join(str(value or "").split())
        if not text or len(text) > 80 or "://" in text or "@" in text:
            continue
        if text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


class FeedbackService:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def record(
        self,
        signal_id: int,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        user_id: int = DEFAULT_LOCAL_USER_ID,
    ):
        if event_type not in FEEDBACK_EVENT_TYPES:
            raise ValueError(f"Unsupported feedback event_type: {event_type}")
        if event_type == "saved":
            return self.set_saved(signal_id, True, payload=payload, user_id=user_id)
        if event_type in {"tracked", "ignored"}:
            return self.set_recommendation_preference(signal_id, event_type, payload=payload, user_id=user_id)
        event_id = self.store.record_feedback(signal_id, event_type, payload, user_id=user_id)
        return {
            "event_id": event_id,
            "signal": self.store.get_signal(signal_id, user_id=user_id),
            "updated_keywords": [],
        }

    def set_saved(self, signal_id: int, saved: bool, payload: Optional[Dict[str, Any]] = None, user_id: int = DEFAULT_LOCAL_USER_ID):
        state = self.store.set_saved_signal(signal_id, saved, user_id=user_id)
        event_id = None
        if state["changed"]:
            event_id = self.store.record_feedback(signal_id, "saved" if saved else "saved_removed", payload or {}, user_id=user_id, materialize=False)
        return {"event_id": event_id, "signal": self.store.get_signal(signal_id, user_id=user_id), "state": state, "updated_keywords": []}

    def set_recommendation_preference(self, signal_id: int, preference: Optional[str], payload: Optional[Dict[str, Any]] = None, user_id: int = DEFAULT_LOCAL_USER_ID):
        state = self.store.set_recommendation_preference(signal_id, preference, user_id=user_id)
        if state["changed"]:
            # Stage 3 records inferred feedback separately from explicit
            # interests.  A single rating must not modify an interest weight,
            # block a source, or alter current ranking.
            self.store.clear_feedback_preference_detail(signal_id, user_id=user_id)
            self.store.record_feedback(signal_id, preference or "preference_cleared", payload or {}, user_id=user_id, materialize=False)
        return {
            "signal": self.store.get_signal(signal_id, user_id=user_id),
            "state": state,
            "updated_keywords": [],
            "learning_status": "observed_only",
        }

    def set_recommendation_reason(
        self, signal_id: int, preference: str, reason_code: str, user_id: int = DEFAULT_LOCAL_USER_ID
    ) -> Dict[str, Any]:
        if reason_code not in FEEDBACK_REASON_CODES.get(preference, set()):
            raise ValueError("Unsupported feedback reason")
        signal = self.store.get_signal(signal_id, user_id=user_id)
        if not signal:
            raise ValueError("Signal not found for this user")
        detail = self._preference_detail(signal, user_id=user_id)
        result = self.store.set_feedback_preference_detail(
            signal_id, preference, reason_code, detail, user_id=user_id
        )
        if result["changed"]:
            self.store.record_feedback(
                signal_id,
                "preference_reason_set",
                {"preference": preference, "reason_code": reason_code},
                user_id=user_id,
                materialize=False,
            )
        return {**result, "learning_status": "observed_only"}

    def _preference_detail(self, signal: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        metadata = signal.get("metadata_json") or {}
        topics = _safe_values(metadata.get("topic_tags") or metadata.get("matched_keywords") or [])
        active_interests = self.store.get_interests(status="active", limit=None, user_id=user_id)
        normalized_topics = {value.casefold() for value in topics}
        related_interests = _safe_values(
            item.get("keyword") for item in active_interests
            if str(item.get("keyword") or "").casefold() in normalized_topics
        )
        profile = self.store.get_profile(user_id=user_id) or {}
        raw = profile.get("raw_onboarding_json") or {}
        preference_map = raw.get("interest_type_preferences") if isinstance(raw, dict) else {}
        selected_ids = valid_type_ids(
            type_id for values in (preference_map or {}).values() if isinstance(values, list) for type_id in values
        )
        category = str(signal.get("category") or "unknown")
        information_type_ids = [
            type_id for type_id in selected_ids
            if category in categories_for_type_ids([type_id])
        ]
        difficulty = str(metadata.get("difficulty") or metadata.get("difficulty_level") or "unknown")
        if difficulty not in {"beginner", "intermediate", "advanced", "unknown"}:
            difficulty = "unknown"
        content_type = str(metadata.get("data_kind") or category or "unknown")
        return {
            "related_interests": related_interests,
            "information_type_ids": information_type_ids,
            "topic_tags": topics,
            "difficulty": difficulty,
            "content_type": content_type[:80] if content_type else "unknown",
        }

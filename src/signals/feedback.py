from typing import Any, Dict, Optional

from src.storage.schemas import FEEDBACK_EVENT_TYPES
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore
from src.context.feedback_learning import apply_feedback_learning


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
        updated_keywords = apply_feedback_learning(self.store, signal_id, event_type, payload or {}, user_id=user_id)
        return {
            "event_id": event_id,
            "signal": self.store.get_signal(signal_id, user_id=user_id),
            "updated_keywords": updated_keywords,
        }

    def set_saved(self, signal_id: int, saved: bool, payload: Optional[Dict[str, Any]] = None, user_id: int = DEFAULT_LOCAL_USER_ID):
        state = self.store.set_saved_signal(signal_id, saved, user_id=user_id)
        event_id = None
        if state["changed"]:
            event_id = self.store.record_feedback(signal_id, "saved" if saved else "saved_removed", payload or {}, user_id=user_id, materialize=False)
        return {"event_id": event_id, "signal": self.store.get_signal(signal_id, user_id=user_id), "state": state, "updated_keywords": []}

    def set_recommendation_preference(self, signal_id: int, preference: Optional[str], payload: Optional[Dict[str, Any]] = None, user_id: int = DEFAULT_LOCAL_USER_ID):
        state = self.store.set_recommendation_preference(signal_id, preference, user_id=user_id)
        updated_keywords = []
        if state["changed"]:
            if state["previous_preference"]:
                apply_feedback_learning(self.store, signal_id, state["previous_preference"], {"reverted": True}, multiplier=-1, user_id=user_id)
            if preference:
                updated_keywords = apply_feedback_learning(self.store, signal_id, preference, payload or {}, user_id=user_id)
            self.store.record_feedback(signal_id, preference or "preference_cleared", payload or {}, user_id=user_id, materialize=False)
        return {"signal": self.store.get_signal(signal_id, user_id=user_id), "state": state, "updated_keywords": updated_keywords}

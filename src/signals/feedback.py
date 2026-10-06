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
        event_id = self.store.record_feedback(signal_id, event_type, payload, user_id=user_id)
        updated_keywords = apply_feedback_learning(
            self.store, signal_id, event_type, payload or {}, user_id=user_id
        )
        return {
            "event_id": event_id,
            "signal": self.store.get_signal(signal_id, user_id=user_id),
            "updated_keywords": updated_keywords,
        }

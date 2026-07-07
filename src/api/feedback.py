from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_store
from src.api.models import FeedbackRequest
from src.signals.feedback import FeedbackService
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["feedback"])


@router.post("/signals/{signal_id}/feedback")
def record_feedback(signal_id: int, request: FeedbackRequest, store: SQLiteStore = Depends(get_store)):
    try:
        result = FeedbackService(store).record(signal_id, request.event_type, request.payload)
        return {"success": True, "data": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/feedback/events")
def list_feedback_events(limit: int = 20, store: SQLiteStore = Depends(get_store)):
    return {"success": True, "events": store.get_recent_feedback_events(limit=max(1, min(limit, 100)))}

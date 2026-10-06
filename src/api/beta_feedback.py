from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["beta"])


class BetaFeedbackRequest(BaseModel):
    feedback_type: str  # bug | 개선제안 | 사용성 | 기타
    message: str
    context: Optional[Dict[str, Any]] = None


@router.post("/beta/feedback")
def submit_beta_feedback(
    request: BetaFeedbackRequest,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not request.message.strip():
        return {"success": False, "error": "message is required"}
    store.save_beta_feedback(
        user_id=current_user.id,
        feedback_type=request.feedback_type or "기타",
        message=request.message.strip(),
        context=request.context or {},
    )
    return {"success": True}

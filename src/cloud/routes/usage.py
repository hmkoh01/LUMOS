import uuid

from fastapi import APIRouter, Depends

from src.cloud.auth import require_session
from src.cloud.database import dumps_metadata, get_connection, utc_now_iso
from src.cloud.schemas import UsageEventRequest

router = APIRouter(prefix="/usage", tags=["cloud-usage"])


@router.post("/events")
def record_usage_event(request: UsageEventRequest, session: dict = Depends(require_session)):
    event_id = f"dev_usage_{uuid.uuid4().hex}"
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO usage_events(id, user_id, device_id, event_type, quantity, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                session["user_id"],
                session.get("device_id"),
                request.event_type,
                request.quantity,
                dumps_metadata(request.metadata),
                utc_now_iso(),
            ),
        )
    return {"success": True, "event_id": event_id}


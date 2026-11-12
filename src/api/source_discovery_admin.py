"""Operator-only source discovery backlog endpoint.

This route deliberately has no user-facing counterpart and exposes only the
candidate metadata stored in the shared queue database.
"""
import hmac
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.engine.operations import queue_path
from src.engine.queue.sqlite_store import SQLiteQueueStore
from src.sources.source_discovery import candidate_can_route

router = APIRouter(tags=["source-discovery-admin"])


def _require_operator(token: Optional[str] = Header(default=None, alias="X-Lumos-Operator-Token")) -> None:
    expected = os.environ.get("LUMOS_SOURCE_DISCOVERY_ADMIN_TOKEN", "").strip()
    # Fail closed: local mode must still configure a distinct operator token.
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


@router.get("/admin/source-discovery/backlog", dependencies=[Depends(_require_operator)])
def get_source_discovery_backlog(limit: int = 100, registration_required: bool = False,
                                 permission_review: bool = False, adapter_needed: bool = False,
                                 entry_kind: Optional[str] = None):
    queue = SQLiteQueueStore(queue_path())
    try:
        candidates = queue.list_source_discovery_backlog(
            limit=limit,
            registration_required=True if registration_required else None,
            permission_review=permission_review,
            adapter_needed=adapter_needed,
            entry_kind=entry_kind,
        )
        for candidate in candidates:
            candidate["routing_eligible"] = candidate_can_route(candidate)
        return {"success": True, "candidates": candidates}
    finally:
        queue.close()

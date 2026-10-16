"""API endpoints for the v2 hybrid briefing engine.

All endpoints are behind the ``LUMOS_ENGINE_V2`` feature flag.
When the flag is off, these routes return 404 (not registered).

GET endpoints never call external APIs or regenerate data.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.engine.config import EngineConfig
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(prefix="/engine", tags=["engine-v2"])


def _get_engine_config() -> EngineConfig:
    return EngineConfig.from_env()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class DismissRequest(BaseModel):
    signal_dedupe_key: str
    period: str = "today"


class UndoDismissRequest(BaseModel):
    signal_dedupe_key: str
    replacement_dedupe_key: Optional[str] = None


class EngineSettingsUpdate(BaseModel):
    signal_count: Optional[int] = None


# ---------------------------------------------------------------------------
# Briefing retrieval (read-only — no LLM, no external calls)
# ---------------------------------------------------------------------------

@router.get("/briefing")
def get_briefing(
    period: str = "today",
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
    config: EngineConfig = Depends(_get_engine_config),
):
    """Retrieve the current briefing for a period.

    Returns pre-generated content from the cache.  Does NOT trigger
    collection, evaluation, or LLM calls.
    """
    if not config.enabled:
        raise HTTPException(status_code=404, detail="Engine v2 is not enabled")

    signals = store.get_signals_for_period(
        {"daily": "today", "weekly": "week", "monthly": "month"}.get(period, period),
        user_id=current_user.id,
    )
    expansion = store.signal_expansion_status(user_id=current_user.id) if period in ("today", "daily") else {"pipeline_run_id": None, "has_more": False}
    return {
        "success": True,
        "period": period,
        "signals": signals,
        "engine_version": "2.0",
        **expansion,
    }


# ---------------------------------------------------------------------------
# Dismiss and backfill
# ---------------------------------------------------------------------------

@router.post("/briefing/dismiss")
def dismiss_signal(
    request: DismissRequest,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
    config: EngineConfig = Depends(_get_engine_config),
):
    """Dismiss a signal card and attempt backfill from reserves.

    Does NOT trigger new external collection.
    """
    if not config.enabled:
        raise HTTPException(status_code=404, detail="Engine v2 is not enabled")

    from src.engine.personalization.backfill import BackfillResult
    # For now, delegate to the existing recommendation preference mechanism
    # and wrap it with backfill metadata.  Full integration will be done
    # when the engine is activated in production.
    from src.signals.feedback import FeedbackService
    try:
        result = FeedbackService(store).set_recommendation_preference(
            _resolve_signal_id(store, request.signal_dedupe_key, current_user.id),
            "ignored",
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "success": True,
        "dismissed": request.signal_dedupe_key,
        "replacement": None,  # Real backfill requires engine activation
        "needs_generation": False,
        "can_undo": True,
    }


@router.post("/briefing/undo-dismiss")
def undo_dismiss(
    request: UndoDismissRequest,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
    config: EngineConfig = Depends(_get_engine_config),
):
    """Undo a previous card dismissal."""
    if not config.enabled:
        raise HTTPException(status_code=404, detail="Engine v2 is not enabled")

    from src.signals.feedback import FeedbackService
    try:
        FeedbackService(store).set_recommendation_preference(
            _resolve_signal_id(store, request.signal_dedupe_key, current_user.id),
            None,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"success": True, "restored": request.signal_dedupe_key}


# ---------------------------------------------------------------------------
# Engine status & budget
# ---------------------------------------------------------------------------

@router.get("/status")
def engine_status(
    config: EngineConfig = Depends(_get_engine_config),
):
    """Return engine feature flag and configuration summary."""
    return {
        "enabled": config.enabled,
        "external_calls_allowed": config.external_calls_allowed,
        "scheduler_enabled": config.collection.scheduler_enabled,
        "max_briefing_display": config.budget.max_briefing_display_count,
        "engine_version": "2.0",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_signal_id(store: SQLiteStore, dedupe_key: str, user_id: int) -> int:
    """Find a signal ID by its dedupe_key."""
    with store.connect() as conn:
        row = conn.execute(
            "SELECT id FROM signals WHERE dedupe_key = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
            (dedupe_key, user_id),
        ).fetchone()
        if not row:
            raise ValueError(f"Signal not found: {dedupe_key}")
        return row["id"]

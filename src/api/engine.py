"""API endpoints for the v2 hybrid briefing engine.

All endpoints are behind the ``LUMOS_ENGINE_V2`` feature flag.
When the flag is off, these routes return 404 (not registered).

GET endpoints never call external APIs or regenerate data.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.engine.config import EngineConfig
from src.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/engine", tags=["engine-v2"])


def _get_engine_config() -> EngineConfig:
    return EngineConfig.from_env()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class DismissRequest(BaseModel):
    signal_id: Optional[int] = None
    signal_dedupe_key: Optional[str] = None
    period: str = "today"


class UndoDismissRequest(BaseModel):
    signal_id: Optional[int] = None
    signal_dedupe_key: Optional[str] = None
    replacement_signal_id: Optional[int] = None


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

    1. Marks the signal as ``ignored`` via FeedbackService (single call,
       no duplicate feedback records or double-counted learning).
    2. Attempts to reveal the next reserve signal as a replacement.
    3. Returns the replacement signal data (or null if no reserves).

    Does NOT trigger new external collection or LLM calls.
    """
    if not config.enabled:
        raise HTTPException(status_code=404, detail="Engine v2 is not enabled")

    signal_id = _resolve_id(store, request.signal_id, request.signal_dedupe_key, current_user.id)

    # Single FeedbackService call — no duplicate records.
    from src.signals.feedback import FeedbackService
    try:
        FeedbackService(store).set_recommendation_preference(
            signal_id, "ignored", user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Attempt backfill from signal reserves.
    replacement = _try_backfill_one(store, current_user.id)

    return {
        "success": True,
        "dismissed_signal_id": signal_id,
        "replacement": replacement,
        "needs_generation": replacement is not None and not replacement.get("display_title_ko"),
        "can_undo": True,
    }


@router.post("/briefing/undo-dismiss")
def undo_dismiss(
    request: UndoDismissRequest,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
    config: EngineConfig = Depends(_get_engine_config),
):
    """Undo a previous card dismissal.

    Clears the ``ignored`` preference. The restored signal will reappear
    on the next ``loadSignals()`` call.
    """
    if not config.enabled:
        raise HTTPException(status_code=404, detail="Engine v2 is not enabled")

    signal_id = _resolve_id(store, request.signal_id, request.signal_dedupe_key, current_user.id)

    from src.signals.feedback import FeedbackService
    try:
        result = FeedbackService(store).set_recommendation_preference(
            signal_id, None, user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    restored = result.get("signal")
    return {
        "success": True,
        "restored_signal_id": signal_id,
        "restored": restored,
    }


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

def _resolve_id(
    store: SQLiteStore,
    signal_id: Optional[int],
    dedupe_key: Optional[str],
    user_id: int,
) -> int:
    """Resolve a signal ID from either signal_id or dedupe_key."""
    if signal_id is not None:
        return signal_id
    if dedupe_key:
        return _resolve_signal_id(store, dedupe_key, user_id)
    raise HTTPException(status_code=400, detail="signal_id or signal_dedupe_key required")


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


def _try_backfill_one(store: SQLiteStore, user_id: int) -> Optional[dict]:
    """Try to reveal one reserve signal as a backfill replacement.

    Uses the existing signal_reserves mechanism (same as "더 보기").
    Returns the revealed signal dict, or None if no reserves.
    """
    try:
        expansion = store.signal_expansion_status(user_id=user_id)
        run_id = expansion.get("pipeline_run_id")
        if not run_id or not expansion.get("has_more"):
            return None

        reserves = store.get_signal_reserves(run_id, limit=1, user_id=user_id)
        if not reserves:
            return None

        from src.signals.generator import SignalGenerator
        generator = SignalGenerator(store)
        run = store.get_pipeline_run(run_id, user_id=user_id) or {}
        current_signals = store.get_today_active_signals(user_id=user_id)
        next_rank = max((int(s.get("rank") or 0) for s in current_signals), default=0) + 1

        reserve_rank, candidate = reserves[0]
        signal = generator._build_signal(
            candidate,
            run.get("profile_snapshot_json", {}),
            run.get("interest_snapshot_json", []),
            next_rank,
        )
        signal["metadata_json"]["is_additional"] = True
        store.reveal_signals(run_id, [(reserve_rank, signal)], user_id=user_id)

        # Return the freshly revealed signal from the DB (authoritative).
        updated = store.get_today_active_signals(user_id=user_id)
        for s in reversed(updated):
            if int(s.get("rank") or 0) == next_rank:
                return s
        return None
    except Exception as exc:
        logger.warning("Backfill failed (non-fatal): %s", exc)
        return None

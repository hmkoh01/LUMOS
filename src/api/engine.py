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

    api_period = {"daily": "today", "weekly": "week", "monthly": "month"}.get(period, period)
    if api_period not in {"today", "week", "month"}:
        raise HTTPException(status_code=400, detail="Unsupported briefing period")
    requested_limit = int(store.get_settings(user_id=current_user.id).get("signal_count", 3))
    display_limit = min(max(1, requested_limit), config.budget.max_briefing_display_count)
    signals = store.get_engine_signals_for_period(api_period, limit=display_limit, user_id=current_user.id)
    engine_period = {"today": "daily", "week": "weekly", "month": "monthly"}[api_period]
    expansion = store.signal_expansion_status(user_id=current_user.id, engine_period=engine_period)
    return {
        "success": True,
        "period": period,
        "signals": signals,
        "display_limit": display_limit,
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
        result = FeedbackService(store).set_recommendation_preference(
            signal_id, "ignored", user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # An idempotent duplicate tap must not consume another reserve card.  The
    # preference write tells us whether this request actually changed feed
    # state; only the first transition to ignored may backfill.
    engine_period = {"today": "daily", "week": "weekly", "month": "monthly", "daily": "daily", "weekly": "weekly", "monthly": "monthly"}.get(request.period)
    if engine_period is None:
        raise HTTPException(status_code=400, detail="Unsupported briefing period")
    replacement = (
        _try_backfill_one(store, current_user.id, engine_period)
        if result["state"].get("changed") else None
    )

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


@router.get("/operations/status")
def engine_operations_status(
    current_user: CurrentUser = Depends(get_current_user),
    config: EngineConfig = Depends(_get_engine_config),
):
    """Read-only operational state for the automatic briefing UI."""
    if not config.enabled:
        raise HTTPException(status_code=404, detail="Engine v2 is not enabled")
    from src.engine.operations import get_engine_operations
    runtime = get_engine_operations()
    if runtime is None:
        return {"enabled": True, "state": "waiting_for_worker", "reason": "runtime_not_started"}
    result = runtime.status(current_user.id)
    latest = result.get("latest_job") or {}
    if result.get("active_collection"):
        result["state"] = "collecting"
    elif result.get("active_generation"):
        result["state"] = "generating"
    elif latest.get("status") == "failed":
        result["state"] = "failed"
        result["reason"] = latest.get("error_message") or "job_failed"
    elif result.get("periods") and not any(value.get("card_count", 0) for value in result["periods"].values()):
        result["state"] = "insufficient"
        result["reason"] = "no_eligible_source_items"
    else:
        result["state"] = "ready"
    return result


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


def _try_backfill_one(store: SQLiteStore, user_id: int, engine_period: str = "daily") -> Optional[dict]:
    """Try to reveal one reserve signal as a backfill replacement.

    Uses the existing signal_reserves mechanism (same as "더 보기").
    Returns the revealed signal dict, or None if no reserves.
    """
    try:
        expansion = store.signal_expansion_status(user_id=user_id, engine_period=engine_period)
        reserve_period = engine_period
        # Legacy/fixture reserve snapshots predate the Engine-period metadata.
        # They remain user-scoped and may be revealed for compatibility, but a
        # real Engine run always uses the period-specific branch above.
        if not expansion.get("pipeline_run_id"):
            expansion = store.signal_expansion_status(user_id=user_id)
            reserve_period = None
        run_id = expansion.get("pipeline_run_id")
        if not run_id or not expansion.get("has_more"):
            return None

        reserves = store.get_signal_reserves(run_id, limit=1, user_id=user_id)
        if not reserves:
            return None

        api_period = {"daily": "today", "weekly": "week", "monthly": "month"}[engine_period]
        current_signals = store.get_engine_signals_for_period(api_period, limit=10_000, user_id=user_id)
        next_rank = max((int(s.get("rank") or 0) for s in current_signals), default=0) + 1

        reserve_rank, candidate = reserves[0]
        # Engine v2 reserves are complete, validated cards prepared during the
        # scheduled generation run.  Never invoke the legacy SignalGenerator
        # here: it may call translation/content helpers and would turn a
        # local dismiss action into an external request.
        if not candidate.get("_engine_signal"):
            return None
        signal = dict(candidate["_engine_signal"])
        signal["rank"] = next_rank
        signal["metadata_json"]["is_additional"] = True
        store.reveal_signals(run_id, [(reserve_rank, signal)], user_id=user_id, engine_period=reserve_period)

        # Return the freshly revealed signal from the DB (authoritative).
        updated = store.get_engine_signals_for_period(api_period, limit=10_000, user_id=user_id)
        if reserve_period is None:
            # Compatibility only for old reserve fixtures that have no
            # engine-period metadata.  Current Engine v2 runs never use this
            # branch.
            updated = store.get_today_active_signals(user_id=user_id)
        for s in reversed(updated):
            if int(s.get("rank") or 0) == next_rank:
                return s
        return None
    except Exception as exc:
        logger.warning("Backfill failed (non-fatal): %s", exc)
        return None

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import get_store
from src.api.pipeline import generate_signals_from_mock_pipeline
from src.context.feedback_learning import apply_feedback_learning
from src.signals.mock_generator import MockSignalGenerator
from src.storage.sqlite_store import SQLiteStore
from src.signals.generator import SignalGenerator

router = APIRouter(tags=["signals"])


class GenerateSignalsRequest(BaseModel):
    mode: str = "mock"
    replace_today: bool = True


class MoreSignalsRequest(BaseModel):
    pipeline_run_id: int


@router.get("/signals/today")
def get_today_signals(store: SQLiteStore = Depends(get_store)):
    return {"success": True, "signals": store.get_today_signals(include_archived=False), **store.signal_expansion_status()}


@router.get("/signals/saved")
def get_saved_signals(store: SQLiteStore = Depends(get_store)):
    return {"success": True, "signals": store.get_saved_signals()}


@router.delete("/signals/{signal_id}/saved")
def delete_saved_signal(signal_id: int, store: SQLiteStore = Depends(get_store)):
    if not store.delete_saved_signal(signal_id):
        raise HTTPException(status_code=404, detail="저장한 소식을 찾지 못했어요.")
    return {"success": True}


@router.get("/signals/feedback/{event_type}")
def get_feedback_signals(event_type: str, store: SQLiteStore = Depends(get_store)):
    return {"success": True, "signals": store.get_feedback_signals(event_type)}


@router.delete("/signals/{signal_id}/feedback/{event_type}")
def clear_feedback_signal(signal_id: int, event_type: str, store: SQLiteStore = Depends(get_store)):
    if not store.has_feedback_signal(signal_id, event_type):
        raise HTTPException(status_code=404, detail="설정한 피드백을 찾지 못했어요.")
    apply_feedback_learning(store, signal_id, event_type, {"reverted": True}, multiplier=-1)
    if not store.clear_feedback_signal(signal_id, event_type):
        raise HTTPException(status_code=404, detail="설정한 피드백을 찾지 못했어요.")
    return {"success": True}


@router.post("/signals/more")
def get_more_signals(request: MoreSignalsRequest, store: SQLiteStore = Depends(get_store)):
    run_id = request.pipeline_run_id
    if store.signal_expansion_status()["pipeline_run_id"] != run_id:
        raise HTTPException(status_code=409, detail="브리핑이 바뀌었어요. 새로고침 후 다시 시도해주세요.")
    generator = SignalGenerator(store)
    run = store.get_pipeline_run(run_id) or {}
    prepared = []
    current_signals = store.get_today_active_signals()
    next_rank = max((int(signal.get("rank") or 0) for signal in current_signals), default=0) + 1
    for reserve_rank, candidate in store.get_signal_reserves(run_id):
        signal = generator._build_signal(candidate, run.get("profile_snapshot_json", {}),
                                         run.get("interest_snapshot_json", []), next_rank)
        signal["metadata_json"]["is_additional"] = True
        # The reserve rank identifies its immutable snapshot row. Card rank is
        # based on what is currently visible, so it always continues 1,2,3,4.
        prepared.append((reserve_rank, signal))
        next_rank += 1
    try:
        store.reveal_signals(run_id, prepared)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"success": True, "signals": store.get_today_active_signals(), **store.signal_expansion_status()}


@router.post("/signals/generate-mock")
def generate_mock_signals(store: SQLiteStore = Depends(get_store)):
    signals = MockSignalGenerator(store).generate_daily_signals()
    return {"success": True, "count": len(signals), "signals": signals}


@router.post("/signals/generate")
def generate_signals(request: Optional[GenerateSignalsRequest] = None, store: SQLiteStore = Depends(get_store)):
    body = request or GenerateSignalsRequest()
    result = generate_signals_from_mock_pipeline(store, replace_today=body.replace_today, mode=body.mode)
    return {
        "success": True,
        "pipeline_run_id": result.get("pipeline_run_id"),
        "mode": body.mode,
        "generated_signal_count": len(result["signals"]),
        "selected_sources": result["selected_sources"],
        "attempted_sources": result["attempted_sources"],
        "successful_sources": result["successful_sources"],
        "failed_sources": result["failed_sources"],
        "skipped_sources": result["skipped_sources"],
        "disabled_sources": result["disabled_sources"],
        "missing_config_sources": result["missing_config_sources"],
        "errors_by_source": result["errors_by_source"],
        "collected_item_count": result["collected_item_count"],
        "top_candidates": result["top_candidates"],
        "signals": result["signals"],
    }

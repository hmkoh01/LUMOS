from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import get_store
from src.api.pipeline import generate_signals_from_mock_pipeline
from src.signals.mock_generator import MockSignalGenerator
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["signals"])


class GenerateSignalsRequest(BaseModel):
    mode: str = "mock"
    replace_today: bool = True


@router.get("/signals/today")
def get_today_signals(store: SQLiteStore = Depends(get_store)):
    return {"success": True, "signals": store.get_today_signals()}


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

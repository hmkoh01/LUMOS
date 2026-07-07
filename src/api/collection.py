from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import get_store
from src.api.pipeline import collect_mock_items, collect_sources
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["collection"])


class CollectRequest(BaseModel):
    mode: str = "mock"


@router.post("/collect/mock")
def collect_mock(store: SQLiteStore = Depends(get_store)):
    result = collect_mock_items(store)
    return {
        "success": True,
        "pipeline_run_id": result.get("pipeline_run_id"),
        "route_count": len(result["routes"]),
        "source_item_count": len(result["source_items"]),
        "selected_sources": result["selected_sources"],
        "source_items": result["source_items"],
    }


@router.post("/collect")
def collect(request: Optional[CollectRequest] = None, store: SQLiteStore = Depends(get_store)):
    mode = request.mode if request else "mock"
    result = collect_sources(store, mode=mode)
    return {
        "success": True,
        "pipeline_run_id": result.get("pipeline_run_id"),
        "mode": mode,
        "selected_sources": result["selected_sources"],
        "collected_count": len(result["source_items"]),
        "attempted_sources": result["attempted_sources"],
        "successful_sources": result["successful_sources"],
        "failed_sources": result["failed_sources"],
        "skipped_sources": result["skipped_sources"],
        "disabled_sources": result["disabled_sources"],
        "missing_config_sources": result["missing_config_sources"],
        "errors_by_source": result["errors_by_source"],
        "source_items": result["source_items"],
    }

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import get_store
from src.context.sync import sync_enabled_connectors, sync_connector
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["context"])


class ContextSyncRequest(BaseModel):
    connector_types: Optional[List[str]] = None
    limit: int = Field(default=100, ge=1, le=1000)


class InterestUpdate(BaseModel):
    weight: Optional[float] = Field(default=None, ge=0)
    category: Optional[str] = None
    status: Optional[str] = None


class InterestCreate(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)


@router.post("/interests")
def add_interest(request: InterestCreate, store: SQLiteStore = Depends(get_store)):
    if not request.keyword.strip():
        raise HTTPException(status_code=422, detail="키워드를 입력해주세요.")
    return {"success": True, "interest": store.add_manual_interest(request.keyword)}


@router.post("/context/sync")
def sync_context(request: ContextSyncRequest, store: SQLiteStore = Depends(get_store)):
    return {"success": True, "result": sync_enabled_connectors(store, request.connector_types, request.limit)}


@router.post("/context/sync/{connector_type}")
def sync_one_connector(connector_type: str, request: ContextSyncRequest = None, store: SQLiteStore = Depends(get_store)):
    request = request or ContextSyncRequest(connector_types=[connector_type])
    connector = next((item for item in store.get_connectors() if item["connector_type"] == connector_type), None)
    if not connector:
        return {"success": False, "error": f"Unknown connector: {connector_type}"}
    return {"success": True, "result": sync_connector(store, connector_type, connector.get("config_json", {}), request.limit)}


@router.get("/context/items")
def get_context_items(connector_type: Optional[str] = None, limit: int = 50, store: SQLiteStore = Depends(get_store)):
    return {"success": True, "items": store.get_context_items(connector_type=connector_type, limit=max(1, min(limit, 200)))}


@router.get("/context/sync-runs")
def get_context_sync_runs(limit: int = 20, store: SQLiteStore = Depends(get_store)):
    return {"success": True, "runs": store.get_recent_context_sync_runs(limit=max(1, min(limit, 100)))}


@router.get("/interests")
def get_interests(
    status: Optional[str] = None,
    limit: int = 50,
    include_muted: bool = False,
    store: SQLiteStore = Depends(get_store),
):
    return {
        "success": True,
        "interests": store.get_interests(
            status=status,
            limit=max(1, min(limit, 500)),
            include_muted=include_muted,
            include_deleted=False,
        ),
    }


@router.put("/interests/{keyword}")
def update_interest(keyword: str, request: InterestUpdate, store: SQLiteStore = Depends(get_store)):
    return {"success": True, "interest": store.update_interest(keyword, request.dict(exclude_none=True))}


@router.post("/interests/{keyword}/mute")
def mute_interest(keyword: str, store: SQLiteStore = Depends(get_store)):
    return {"success": True, "interest": store.mute_interest(keyword)}


@router.post("/interests/{keyword}/unmute")
def unmute_interest(keyword: str, store: SQLiteStore = Depends(get_store)):
    return {"success": True, "interest": store.unmute_interest(keyword)}


@router.delete("/interests/{keyword}")
def delete_interest(keyword: str, store: SQLiteStore = Depends(get_store)):
    return {"success": True, "deleted": store.delete_interest(keyword)}


@router.get("/interests/{keyword}/evidence")
def get_interest_evidence(keyword: str, store: SQLiteStore = Depends(get_store)):
    return {"success": True, "evidence": store.get_interest_evidence(keyword)}


@router.post("/context/prune-interests")
def prune_interests(max_keywords: Optional[int] = None, store: SQLiteStore = Depends(get_store)):
    settings = store.get_sync_settings()
    limit = max_keywords or settings["max_interest_keywords"]
    return {"success": True, "result": store.prune_interests(limit)}

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import get_store
from src.sources.collector_registry import CollectorRegistry
from src.sources.source_registry import get_source_catalog
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["sources"])


class SourceConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    config_json: Optional[Dict[str, Any]] = None


class SeedDefaultsRequest(BaseModel):
    overwrite: bool = False


@router.get("/sources/catalog")
def get_catalog(store: SQLiteStore = Depends(get_store)):
    configs = store.get_source_configs()
    registry = CollectorRegistry()
    return {
        "success": True,
        "sources": get_source_catalog(configs, status_lookup=lambda source_id: registry.support_status(source_id, mode="live")),
    }


@router.get("/sources/configs")
def get_configs(store: SQLiteStore = Depends(get_store)):
    return {"success": True, "configs": store.get_source_configs()}


@router.put("/sources/configs/{source_id}")
def update_config(source_id: str, update: SourceConfigUpdate, store: SQLiteStore = Depends(get_store)):
    config = store.upsert_source_config(
        source_id,
        enabled=update.enabled,
        priority=update.priority,
        config=update.config_json,
    )
    return {"success": True, "config": config}


@router.post("/sources/configs/seed-defaults")
def seed_defaults(request: Optional[SeedDefaultsRequest] = None, store: SQLiteStore = Depends(get_store)):
    body = request or SeedDefaultsRequest()
    return {"success": True, "configs": store.seed_default_source_configs(overwrite=body.overwrite)}

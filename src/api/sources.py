import os
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.sources.collector_registry import CollectorRegistry
from src.sources.source_registry import get_source_catalog
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["sources"])


class SourceConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    selection_mode: Optional[Literal["auto", "enabled", "disabled"]] = None
    priority: Optional[int] = None
    config_json: Optional[Dict[str, Any]] = None


class SeedDefaultsRequest(BaseModel):
    overwrite: bool = False


@router.get("/sources/catalog")
def get_catalog(
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    configs = store.get_source_configs(user_id=current_user.id)
    registry = CollectorRegistry()
    sources = get_source_catalog(configs, status_lookup=lambda source_id: registry.support_status(source_id, mode="live"))
    for source in sources:
        if source["source_id"] == "youtube":
            source["api_key_ready"] = bool(os.environ.get("YOUTUBE_API_KEY", "").strip())
    from src.sources.router import SourceRouter
    settings = store.get_settings(user_id=current_user.id)
    profile = store.get_profile(user_id=current_user.id) or {}
    interests = store.get_interests(limit=50, user_id=current_user.id)
    recommended = {route["source"] for route in SourceRouter().plan(profile, settings, [], interests, source_configs=configs)}
    for source in sources:
        source["is_auto_recommended"] = source["source_id"] in recommended
        source["effective_enabled"] = source.get("selection_mode") == "enabled" or (
            source.get("selection_mode") == "auto" and source["is_auto_recommended"]
        )
    return {
        "success": True,
        "sources": sources,
    }


@router.get("/sources/configs")
def get_configs(
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    return {"success": True, "configs": store.get_source_configs(user_id=current_user.id)}


@router.put("/sources/configs/{source_id}")
def update_config(
    source_id: str,
    update: SourceConfigUpdate,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    config = store.upsert_source_config(
        source_id,
        enabled=update.enabled,
        priority=update.priority,
        config=update.config_json,
        selection_mode=update.selection_mode,
        user_id=current_user.id,
    )
    return {"success": True, "config": config}


@router.post("/sources/configs/seed-defaults")
def seed_defaults(
    request: Optional[SeedDefaultsRequest] = None,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    body = request or SeedDefaultsRequest()
    return {
        "success": True,
        "configs": store.seed_default_source_configs(overwrite=body.overwrite, user_id=current_user.id),
    }

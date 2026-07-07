from fastapi import APIRouter, Depends

from src.api.dependencies import get_store
from src.api.models import SettingsUpdate
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["settings"])


@router.get("/settings")
def get_settings(store: SQLiteStore = Depends(get_store)):
    return {"success": True, "settings": store.get_settings()}


@router.put("/settings")
def update_settings(request: SettingsUpdate, store: SQLiteStore = Depends(get_store)):
    return {"success": True, "settings": store.update_settings(request.dict(exclude_unset=True))}


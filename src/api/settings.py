from fastapi import APIRouter, Depends

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.models import SettingsUpdate
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["settings"])


@router.get("/settings")
def get_settings(
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    return {"success": True, "settings": store.get_settings(user_id=current_user.id)}


@router.put("/settings")
def update_settings(
    request: SettingsUpdate,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    return {
        "success": True,
        "settings": store.update_settings(request.dict(exclude_unset=True), user_id=current_user.id),
    }

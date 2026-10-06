from fastapi import APIRouter, Depends

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.pipeline import preview_routes
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["routes"])


@router.post("/routes/preview")
def routes_preview(
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    routes = preview_routes(store, user_id=current_user.id)
    return {
        "success": True,
        "selected_sources": [route["source"] for route in routes],
        "routes": routes,
    }

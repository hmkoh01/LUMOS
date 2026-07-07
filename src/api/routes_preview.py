from fastapi import APIRouter, Depends

from src.api.dependencies import get_store
from src.api.pipeline import preview_routes
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["routes"])


@router.post("/routes/preview")
def routes_preview(store: SQLiteStore = Depends(get_store)):
    routes = preview_routes(store)
    return {
        "success": True,
        "selected_sources": [route["source"] for route in routes],
        "routes": routes,
    }


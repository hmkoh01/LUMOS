from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.models import ConnectorUpdate
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["connectors"])


@router.get("/connectors")
def get_connectors(
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    return {"success": True, "connectors": store.get_connectors(user_id=current_user.id)}


@router.put("/connectors/{connector_type}")
def update_connector(
    connector_type: str,
    request: ConnectorUpdate,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        connector = store.update_connector(
            connector_type, request.enabled, request.config, user_id=current_user.id
        )
        return {"success": True, "connector": connector}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

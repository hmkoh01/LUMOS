from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_store
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["pipeline"])


@router.get("/pipeline/runs")
def list_pipeline_runs(limit: int = 10, store: SQLiteStore = Depends(get_store)):
    return {
        "success": True,
        "runs": store.get_recent_pipeline_runs(limit=max(1, min(limit, 50))),
    }


@router.get("/pipeline/runs/{run_id}")
def get_pipeline_run(run_id: int, store: SQLiteStore = Depends(get_store)):
    run = store.get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return {"success": True, "run": run}

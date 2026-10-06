from typing import Any, Dict, List

from src.signals.pipeline import SignalPipeline
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


def preview_routes(
    store: SQLiteStore, user_id: int = DEFAULT_LOCAL_USER_ID
) -> List[Dict[str, Any]]:
    return SignalPipeline(store).preview_routes(user_id=user_id)


def persist_routes(store: SQLiteStore, planned_routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return SignalPipeline(store).persist_routes(planned_routes)


def collect_mock_items(
    store: SQLiteStore,
    planned_routes: List[Dict[str, Any]] = None,
    user_id: int = DEFAULT_LOCAL_USER_ID,
) -> Dict[str, Any]:
    pipeline = SignalPipeline(store)
    if planned_routes:
        return pipeline.collect_mock_items(planned_routes, user_id=user_id)
    return pipeline.collect_mock(user_id=user_id)


def collect_sources(
    store: SQLiteStore, mode: str = "mock", user_id: int = DEFAULT_LOCAL_USER_ID
) -> Dict[str, Any]:
    return SignalPipeline(store).collect_sources(mode=mode, user_id=user_id)


def generate_signals_from_mock_pipeline(
    store: SQLiteStore,
    replace_today: bool = True,
    mode: str = "mock",
    user_id: int = DEFAULT_LOCAL_USER_ID,
) -> Dict[str, Any]:
    return SignalPipeline(store).generate_daily_signals(
        replace_today=replace_today, mode=mode, user_id=user_id
    )

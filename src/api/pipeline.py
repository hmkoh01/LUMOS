from typing import Any, Dict, List

from src.signals.pipeline import SignalPipeline
from src.storage.sqlite_store import SQLiteStore


def preview_routes(store: SQLiteStore) -> List[Dict[str, Any]]:
    return SignalPipeline(store).preview_routes()


def persist_routes(store: SQLiteStore, planned_routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return SignalPipeline(store).persist_routes(planned_routes)


def collect_mock_items(store: SQLiteStore, planned_routes: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    pipeline = SignalPipeline(store)
    if planned_routes:
        return pipeline.collect_mock_items(planned_routes)
    return pipeline.collect_mock()


def collect_sources(store: SQLiteStore, mode: str = "mock") -> Dict[str, Any]:
    return SignalPipeline(store).collect_sources(mode=mode)


def generate_signals_from_mock_pipeline(
    store: SQLiteStore,
    replace_today: bool = True,
    mode: str = "mock",
) -> Dict[str, Any]:
    return SignalPipeline(store).generate_daily_signals(replace_today=replace_today, mode=mode)

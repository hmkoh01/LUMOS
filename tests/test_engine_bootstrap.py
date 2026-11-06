from src.engine.bootstrap import initialize_engine, reset_engine_bootstrap_for_test
from src.engine.config import EngineConfig
from src.engine.queue.worker import get_handler
from src.storage.sqlite_store import SQLiteStore


def test_disabled_engine_does_not_register_or_create_provider(tmp_path):
    reset_engine_bootstrap_for_test()
    assert initialize_engine(SQLiteStore(tmp_path / "app.sqlite"), EngineConfig(enabled=False)) is None


def test_enabled_engine_registers_once_without_starting_worker(tmp_path, monkeypatch):
    reset_engine_bootstrap_for_test()
    cache_path = tmp_path / "persistent" / "engine.sqlite"
    monkeypatch.setenv("LUMOS_ENGINE_CACHE_DB_PATH", str(cache_path))
    service = initialize_engine(SQLiteStore(tmp_path / "app.sqlite"), EngineConfig(enabled=True))
    assert service is not None
    assert initialize_engine(SQLiteStore(tmp_path / "other.sqlite"), EngineConfig(enabled=True)) is service
    assert cache_path.exists()
    assert get_handler("generate_briefing") is not None
    reset_engine_bootstrap_for_test()

from src.engine.bootstrap import initialize_engine
from src.engine.config import EngineConfig
from src.storage.sqlite_store import SQLiteStore
from src.engine.operations import start_engine_operations, stop_engine_operations


def initialize_app():
    store = SQLiteStore()
    config = EngineConfig.from_env()
    initialize_engine(store, config)
    # Explicit feature flags are required; imports alone remain side-effect
    # free.  The runtime owns workers and the Asia/Seoul schedule.
    start_engine_operations(store, config)


def shutdown_app():
    stop_engine_operations()


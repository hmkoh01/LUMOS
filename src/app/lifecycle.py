from src.engine.bootstrap import initialize_engine
from src.engine.config import EngineConfig
from src.storage.sqlite_store import SQLiteStore


def initialize_app():
    store = SQLiteStore()
    # This is wiring only.  WorkerPool/Scheduler are intentionally owned by
    # explicit operational commands and cannot start during web-app import.
    initialize_engine(store, EngineConfig.from_env())


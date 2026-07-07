from functools import lru_cache

from src.storage.sqlite_store import SQLiteStore


@lru_cache(maxsize=1)
def get_store() -> SQLiteStore:
    return SQLiteStore()


from src.storage.sqlite_store import SQLiteStore


class InterestGraph:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def list(self, limit: int = 50):
        return self.store.get_interests(limit=limit)


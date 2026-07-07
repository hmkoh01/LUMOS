from src.storage.sqlite_store import SQLiteStore


class ProfileService:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def get(self):
        return self.store.get_profile()


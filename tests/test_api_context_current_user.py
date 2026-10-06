import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.context import router as context_router
from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class ApiContextCurrentUserTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "api-context.db")
        with self.store.connect() as conn:
            conn.execute("INSERT INTO users (external_id) VALUES ('context-api-a')")
            conn.execute("INSERT INTO users (external_id) VALUES ('context-api-b')")
            self.user_a = conn.execute("SELECT id FROM users WHERE external_id = 'context-api-a'").fetchone()[0]
            self.user_b = conn.execute("SELECT id FROM users WHERE external_id = 'context-api-b'").fetchone()[0]

        self.selected_user = self.user_a
        self.app = FastAPI()
        self.app.include_router(context_router, prefix="/api/v1")
        self.app.dependency_overrides[get_store] = lambda: self.store
        self.app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=self.selected_user)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_context_item_api_hides_other_users_sensitive_values(self):
        self.store.upsert_context_item(
            {"connector_type": "local_files", "item_id": "a", "title": "A note", "text_snippet": "A-only snippet", "path": "C:/a/private.txt"},
            user_id=self.user_a,
        )
        self.store.upsert_context_item(
            {"connector_type": "local_files", "item_id": "b", "title": "B note", "text_snippet": "B-only snippet", "path": "C:/b/private.txt"},
            user_id=self.user_b,
        )
        response = self.client.get("/api/v1/context/items", params={"search": "snippet"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["text_snippet"], "A-only snippet")
        self.assertEqual(response.json()["items"][0]["path"], "C:/a/private.txt")

        self.selected_user = self.user_b
        response = self.client.get("/api/v1/context/items", params={"connector_type": "local_files"})
        self.assertEqual(len(response.json()["items"]), 1)
        self.assertEqual(response.json()["items"][0]["text_snippet"], "B-only snippet")
        self.assertNotIn("A-only", str(response.json()))

    def test_default_local_user_remains_context_api_fallback(self):
        local_id = self.store.upsert_context_item(
            {"connector_type": "browser_history", "item_id": "local", "title": "Local", "text_snippet": "local snippet"}
        )
        self.app.dependency_overrides.pop(get_current_user)
        response = self.client.get("/api/v1/context/items")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["items"]], [local_id])
        self.assertEqual(response.json()["items"][0]["user_id"], DEFAULT_LOCAL_USER_ID)


if __name__ == "__main__":
    unittest.main()

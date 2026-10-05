import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from src.api.dependencies import get_store
from src.app.main import app
from src.storage.sqlite_store import SQLiteStore


class ManualInterestsTest(unittest.TestCase):
    def test_interest_list_keeps_added_order_when_weight_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "test.db")
            store.add_manual_interest("first interest")
            store.add_manual_interest("second interest")
            store.update_interest("first interest", weight=10)
            store.update_interest("second interest", weight=0.1)

            interests = store.get_interests(include_deleted=False)
            self.assertEqual([interest["keyword"] for interest in interests], ["first interest", "second interest"])

    def test_muted_interests_are_listed_after_active_interests(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "test.db")
            store.add_manual_interest("highest weight")
            store.add_manual_interest("active interest")
            store.update_interest("highest weight", weight=10)
            store.mute_interest("highest weight")

            interests = store.get_interests(include_muted=True, include_deleted=False)
            self.assertEqual([interest["keyword"] for interest in interests], ["active interest", "highest weight"])

    def test_add_persist_deduplicate_delete_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.db"
            store = SQLiteStore(path)
            app.dependency_overrides[get_store] = lambda: store
            try:
                with TestClient(app) as client:
                    for keyword in ("", "   ", "x" * 101):
                        self.assertEqual(client.post("/api/v1/interests", json={"keyword": keyword}).status_code, 422)
                    response = client.post("/api/v1/interests", json={"keyword": "  콘텐츠   마케팅  "})
                    self.assertEqual(response.status_code, 200)
                    interest = response.json()["interest"]
                    self.assertEqual(interest["keyword"], "콘텐츠 마케팅")
                    self.assertEqual(interest["source"], "manual")
                    client.post("/api/v1/interests", json={"keyword": "콘텐츠 마케팅"})
                    self.assertEqual(len(client.get("/api/v1/interests").json()["interests"]), 1)
                    client.delete("/api/v1/interests/콘텐츠 마케팅")
                    restored = client.post("/api/v1/interests", json={"keyword": "콘텐츠 마케팅"}).json()["interest"]
                    self.assertEqual(restored["id"], interest["id"])
                    self.assertEqual(restored["status"], "active")
                    persisted = SQLiteStore(path)
                    self.assertEqual(len(persisted.get_interests()), 1)
                    self.assertTrue(persisted.get_settings()["onboarding_completed"])
            finally:
                app.dependency_overrides.pop(get_store, None)


if __name__ == "__main__":
    unittest.main()

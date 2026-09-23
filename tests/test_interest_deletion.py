import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.dependencies import get_store
from src.app.main import app
from src.storage.sqlite_store import SQLiteStore


class InterestDeletionTest(unittest.TestCase):
    def test_deleted_interests_stay_out_of_list_after_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "test.db")
            for keyword, weight in [("deleted-keyword", 100), ("active-keyword", 2), ("muted-keyword", 1)]:
                store.upsert_interest(keyword, "test", weight, "manual", {})
            store.mute_interest("muted-keyword")
            app.dependency_overrides[get_store] = lambda: store
            try:
                client = TestClient(app)
                response = client.delete("/api/v1/interests/deleted-keyword")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["deleted"], 1)
                for _ in range(2):
                    response = client.get("/api/v1/interests?include_muted=true&limit=2")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        {item["keyword"] for item in response.json()["interests"]},
                        {"active-keyword", "muted-keyword"},
                    )
                self.assertTrue(store.is_interest_blocked("deleted-keyword"))
                client.delete("/api/v1/interests/active-keyword")
                client.delete("/api/v1/interests/muted-keyword")
                self.assertEqual(client.get("/api/v1/interests?include_muted=true").json()["interests"], [])
            finally:
                app.dependency_overrides.pop(get_store, None)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.connectors import router as connectors_router
from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class ApiConnectorsCurrentUserTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "api-connectors.db")
        with self.store.connect() as conn:
            conn.execute("INSERT INTO users (external_id) VALUES ('connector-api-a')")
            conn.execute("INSERT INTO users (external_id) VALUES ('connector-api-b')")
            self.user_a = conn.execute("SELECT id FROM users WHERE external_id = 'connector-api-a'").fetchone()[0]
            self.user_b = conn.execute("SELECT id FROM users WHERE external_id = 'connector-api-b'").fetchone()[0]

        self.selected_user = self.user_a
        self.app = FastAPI()
        self.app.include_router(connectors_router, prefix="/api/v1")
        self.app.dependency_overrides[get_store] = lambda: self.store
        self.app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=self.selected_user)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_connectors_and_settings_follow_current_user(self):
        response = self.client.put(
            "/api/v1/connectors/browser_history",
            json={"enabled": True, "config": {"profile": "a"}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["connector"]["config_json"], {"profile": "a"})

        self.selected_user = self.user_b
        b_connectors = self.client.get("/api/v1/connectors").json()["connectors"]
        b_browser = next(item for item in b_connectors if item["connector_type"] == "browser_history")
        self.assertEqual(b_browser["config_json"], {})
        self.assertTrue(b_browser["enabled"])
        response = self.client.put(
            "/api/v1/connectors/browser_history",
            json={"enabled": False, "config": {"profile": "b"}},
        )
        self.assertEqual(response.status_code, 200)

        self.selected_user = self.user_a
        a_browser = next(
            item for item in self.client.get("/api/v1/connectors").json()["connectors"]
            if item["connector_type"] == "browser_history"
        )
        self.assertEqual((a_browser["enabled"], a_browser["config_json"]), (True, {"profile": "a"}))
        self.assertTrue(self.store.get_settings(user_id=self.user_a)["enabled_connectors_json"]["browser_history"])
        self.assertFalse(self.store.get_settings(user_id=self.user_b)["enabled_connectors_json"]["browser_history"])

    def test_default_local_user_remains_the_api_fallback(self):
        self.app.dependency_overrides.pop(get_current_user)
        response = self.client.put(
            "/api/v1/connectors/local_files",
            json={"enabled": True, "config": {"folders": ["C:/local"]}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["connector"]["user_id"], DEFAULT_LOCAL_USER_ID)
        self.assertEqual(
            self.store.get_connector("local_files")["config_json"], {"folders": ["C:/local"]}
        )


if __name__ == "__main__":
    unittest.main()

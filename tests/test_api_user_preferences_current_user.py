import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.context import router as context_router
from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.profile import router as profile_router
from src.api.settings import router as settings_router
from src.api.sources import router as sources_router
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class ApiUserPreferencesCurrentUserTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "api-preferences.db")
        with self.store.connect() as conn:
            conn.execute("INSERT INTO users (external_id) VALUES ('preferences-a')")
            conn.execute("INSERT INTO users (external_id) VALUES ('preferences-b')")
            self.user_a = conn.execute(
                "SELECT id FROM users WHERE external_id = 'preferences-a'"
            ).fetchone()[0]
            self.user_b = conn.execute(
                "SELECT id FROM users WHERE external_id = 'preferences-b'"
            ).fetchone()[0]

        self.selected_user = self.user_a
        self.app = FastAPI()
        self.app.include_router(profile_router, prefix="/api/v1")
        self.app.include_router(settings_router, prefix="/api/v1")
        self.app.include_router(context_router, prefix="/api/v1")
        self.app.include_router(sources_router, prefix="/api/v1")
        self.app.dependency_overrides[get_store] = lambda: self.store
        self.app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=self.selected_user)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def onboarding(self, role, keyword, signal_count):
        response = self.client.post(
            "/api/v1/onboarding",
            json={
                "role": role,
                "goals": [f"{role} goal"],
                "interest_types": [keyword],
                "keywords": [keyword],
                "preferred_signal_count": signal_count,
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_profile_settings_interests_and_source_configs_follow_current_user(self):
        self.onboarding("A role", "shared-topic", 2)
        self.selected_user = self.user_b
        self.onboarding("B role", "shared-topic", 5)

        self.assertEqual(self.client.get("/api/v1/profile").json()["profile"]["role"], "B role")
        self.assertEqual(self.client.get("/api/v1/settings").json()["settings"]["signal_count"], 5)
        self.assertEqual(
            [item["keyword"] for item in self.client.get("/api/v1/interests").json()["interests"]],
            ["shared-topic", "B role"],
        )

        self.selected_user = self.user_a
        self.assertEqual(self.client.get("/api/v1/profile").json()["profile"]["role"], "A role")
        self.assertEqual(self.client.get("/api/v1/settings").json()["settings"]["signal_count"], 2)
        self.assertEqual(
            self.client.put("/api/v1/settings", json={"briefing_time": "07:30"}).status_code,
            200,
        )
        self.assertEqual(
            self.client.put("/api/v1/interests/shared-topic", json={"weight": 7}).status_code,
            200,
        )
        self.assertEqual(self.client.post("/api/v1/interests/shared-topic/mute").status_code, 200)
        self.assertEqual(self.client.delete("/api/v1/interests/A%20role").json()["deleted"], 1)
        self.assertEqual(
            self.client.put(
                "/api/v1/sources/configs/rss",
                json={"enabled": True, "priority": 91, "config_json": {"feed_urls": ["https://a.test/rss"]}},
            ).status_code,
            200,
        )

        self.selected_user = self.user_b
        b_interests = self.client.get("/api/v1/interests", params={"include_muted": "true"}).json()["interests"]
        self.assertEqual(next(item for item in b_interests if item["keyword"] == "shared-topic")["status"], "active")
        self.assertIn("B role", [item["keyword"] for item in b_interests])
        self.assertEqual(self.client.get("/api/v1/settings").json()["settings"]["briefing_time"], "08:00")
        self.assertEqual(
            self.client.put(
                "/api/v1/sources/configs/rss",
                json={"enabled": False, "priority": 11, "config_json": {"feed_urls": ["https://b.test/rss"]}},
            ).status_code,
            200,
        )
        b_rss = next(item for item in self.client.get("/api/v1/sources/configs").json()["configs"] if item["source_id"] == "rss")
        self.assertEqual((b_rss["enabled"], b_rss["priority"], b_rss["config_json"]["feed_urls"]), (False, 11, ["https://b.test/rss"]))

        self.selected_user = self.user_a
        a_rss = next(item for item in self.client.get("/api/v1/sources/configs").json()["configs"] if item["source_id"] == "rss")
        self.assertEqual((a_rss["enabled"], a_rss["priority"], a_rss["config_json"]["feed_urls"]), (True, 91, ["https://a.test/rss"]))

    def test_default_local_user_dependency_remains_compatible(self):
        self.app.dependency_overrides.pop(get_current_user)
        response = self.client.put("/api/v1/settings", json={"signal_count": 4})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["settings"]["signal_count"], 4)
        self.assertEqual(self.store.get_settings(user_id=DEFAULT_LOCAL_USER_ID)["signal_count"], 4)
        self.assertEqual(self.client.post("/api/v1/interests", json={"keyword": "local-topic"}).status_code, 200)
        self.assertEqual(
            [item["keyword"] for item in self.client.get("/api/v1/interests").json()["interests"]],
            ["local-topic"],
        )


if __name__ == "__main__":
    unittest.main()

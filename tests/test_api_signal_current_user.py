import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.feedback import router as feedback_router
from src.api.signals import router as signals_router
from src.sources.collectors.base import CollectedItem, CollectorResult
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class ApiSignalCurrentUserTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "api-signals.db")
        with self.store.connect() as conn:
            conn.execute("INSERT INTO users (external_id) VALUES ('api-a')")
            conn.execute("INSERT INTO users (external_id) VALUES ('api-b')")
            self.user_a = conn.execute("SELECT id FROM users WHERE external_id = 'api-a'").fetchone()[0]
            self.user_b = conn.execute("SELECT id FROM users WHERE external_id = 'api-b'").fetchone()[0]

        self.selected_user = self.user_a
        self.app = FastAPI()
        self.app.include_router(signals_router, prefix="/api/v1")
        self.app.include_router(feedback_router, prefix="/api/v1")
        self.app.dependency_overrides[get_store] = lambda: self.store
        self.app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=self.selected_user)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    @staticmethod
    def signal(title, url):
        return {
            "title": title,
            "summary": "Summary",
            "why_it_matters": "Why it matters",
            "source_name": "Mock",
            "source_url": url,
            "status": "active",
        }

    @staticmethod
    def reserve(title, url):
        return {"title": title, "summary": "Summary", "url": url, "source": "mock"}

    def create_expandable_run(self, user_id, prefix):
        run_id = self.store.create_pipeline_run("signal_generation", user_id=user_id)
        primary_id = self.store.create_signal(
            self.signal(f"{prefix} primary", f"https://example.test/{prefix}/primary"),
            pipeline_run_id=run_id,
            user_id=user_id,
        )
        self.store.save_signal_reserves(
            run_id,
            [self.reserve(f"{prefix} reserve", f"https://example.test/{prefix}/reserve")],
            1,
            user_id=user_id,
        )
        return run_id, primary_id

    def test_signals_feedback_and_reserves_follow_current_user(self):
        a_run, a_signal = self.create_expandable_run(self.user_a, "a")
        b_run, b_signal = self.create_expandable_run(self.user_b, "b")

        response = self.client.get("/api/v1/signals?period=today")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["signals"]], [a_signal])

        self.selected_user = self.user_b
        self.assertEqual(
            [item["id"] for item in self.client.get("/api/v1/signals?period=today").json()["signals"]],
            [b_signal],
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/signals/{a_signal}/feedback", json={"event_type": "saved", "payload": {}}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post("/api/v1/signals/more", json={"pipeline_run_id": a_run}).status_code,
            409,
        )
        self.assertEqual(self.store.get_signal_reserves(a_run, user_id=self.user_a)[0][0], 2)

        self.assertEqual(
            self.client.post(
                f"/api/v1/signals/{b_signal}/feedback", json={"event_type": "ignored", "payload": {}}
            ).status_code,
            200,
        )
        self.assertEqual([item["id"] for item in self.client.get("/api/v1/signals/feedback/ignored").json()["signals"]], [b_signal])
        self.assertEqual(self.client.get("/api/v1/signals/saved").json()["signals"], [])

        self.selected_user = self.user_a
        self.assertEqual(
            self.client.post(
                f"/api/v1/signals/{a_signal}/feedback", json={"event_type": "saved", "payload": {}}
            ).status_code,
            200,
        )
        self.assertEqual([item["id"] for item in self.client.get("/api/v1/signals/saved").json()["signals"]], [a_signal])
        self.assertEqual(self.client.delete(f"/api/v1/signals/{b_signal}/saved").status_code, 404)
        self.assertEqual(self.client.post("/api/v1/signals/more", json={"pipeline_run_id": a_run}).status_code, 200)
        self.assertEqual(self.store.get_signal_reserves(a_run, user_id=self.user_a), [])
        self.assertEqual(len(self.store.get_signal_reserves(b_run, user_id=self.user_b)), 1)
        self.assertTrue(all(event["user_id"] == self.user_a for event in self.client.get("/api/v1/feedback/events").json()["events"]))

    def test_generation_uses_current_user_and_default_dependency_keeps_local_flow(self):
        self.store.update_settings({"signal_count": 1}, user_id=self.user_a)
        self.store.add_manual_interest("alpha", user_id=self.user_a)
        for config in self.store.get_source_configs(user_id=self.user_a):
            self.store.upsert_source_config(
                config["source_id"], enabled=config["source_id"] == "hackernews", user_id=self.user_a
            )

        def collect(source, queries, limit, mode):
            return CollectorResult(
                source=source,
                items=[
                    CollectedItem(
                        source=source,
                        source_item_id="alpha-1",
                        url="https://example.test/alpha",
                        title="alpha update",
                        raw_json={"mock": True},
                    )
                ],
            )

        with patch("src.signals.pipeline.CollectorRegistry.collect", side_effect=collect):
            response = self.client.post("/api/v1/signals/generate", json={"mode": "mock"})
        self.assertEqual(response.status_code, 200)
        generated = response.json()["signals"]
        self.assertEqual(len(generated), 1)
        self.assertEqual(generated[0]["user_id"], self.user_a)
        self.assertEqual(
            self.store.get_pipeline_run(response.json()["pipeline_run_id"], user_id=self.user_a)["status"], "completed"
        )
        self.assertEqual(self.store.get_today_active_signals(user_id=self.user_b), [])

        self.app.dependency_overrides.pop(get_current_user)
        local_id = self.store.create_signal(self.signal("local", "https://example.test/local"))
        response = self.client.get("/api/v1/signals/today")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["signals"]], [local_id])
        self.assertEqual(self.store.get_signal(local_id)["user_id"], DEFAULT_LOCAL_USER_ID)


if __name__ == "__main__":
    unittest.main()

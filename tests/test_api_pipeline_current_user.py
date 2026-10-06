import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.chat import router as chat_router
from src.api.collection import router as collection_router
from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.pipeline_runs import router as pipeline_runs_router
from src.api.routes_preview import router as routes_preview_router
from src.sources.collectors.base import CollectedItem, CollectorResult
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class ApiPipelineCurrentUserTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "api-pipeline.db")
        with self.store.connect() as conn:
            conn.execute("INSERT INTO users (external_id) VALUES ('pipeline-api-a')")
            conn.execute("INSERT INTO users (external_id) VALUES ('pipeline-api-b')")
            self.user_a = conn.execute(
                "SELECT id FROM users WHERE external_id = 'pipeline-api-a'"
            ).fetchone()[0]
            self.user_b = conn.execute(
                "SELECT id FROM users WHERE external_id = 'pipeline-api-b'"
            ).fetchone()[0]

        self.selected_user = self.user_a
        self.app = FastAPI()
        self.app.include_router(routes_preview_router, prefix="/api/v1")
        self.app.include_router(collection_router, prefix="/api/v1")
        self.app.include_router(pipeline_runs_router, prefix="/api/v1")
        self.app.include_router(chat_router, prefix="/api/v1")
        self.app.dependency_overrides[get_store] = lambda: self.store
        self.app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=self.selected_user)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def configure_user(self, user_id, keyword, enabled_source):
        self.store.add_manual_interest(keyword, user_id=user_id)
        for config in self.store.get_source_configs(user_id=user_id):
            self.store.upsert_source_config(
                config["source_id"], enabled=config["source_id"] == enabled_source, user_id=user_id
            )

    @staticmethod
    def collect(source, queries, limit, mode):
        return CollectorResult(
            source=source,
            items=[
                CollectedItem(
                    source=source,
                    source_item_id=f"{source}-item",
                    url=f"https://example.test/{source}",
                    title=f"{source} item",
                    raw_json={"mock": True},
                )
            ],
        )

    def test_routes_collection_runs_and_chat_use_current_user(self):
        self.configure_user(self.user_a, "alpha-topic", "hackernews")
        self.configure_user(self.user_b, "beta-topic", "github")

        a_preview = self.client.post("/api/v1/routes/preview").json()
        self.assertEqual(set(a_preview["selected_sources"]), {"hackernews"})
        self.assertIn("alpha-topic", " ".join(route["reason"] for route in a_preview["routes"]))

        with patch("src.signals.pipeline.CollectorRegistry.collect", side_effect=self.collect):
            collection = self.client.post("/api/v1/collect/mock")
        self.assertEqual(collection.status_code, 200)
        a_run_id = collection.json()["pipeline_run_id"]
        self.assertEqual(self.store.get_pipeline_run(a_run_id, user_id=self.user_a)["status"], "completed")
        self.assertIsNone(self.store.get_pipeline_run(a_run_id, user_id=self.user_b))

        a_signal = self.store.create_signal(
            {
                "title": "alpha briefing",
                "summary": "alpha summary",
                "why_it_matters": "alpha",
                "source_url": "https://example.test/alpha",
                "status": "active",
            },
            user_id=self.user_a,
        )
        b_signal = self.store.create_signal(
            {
                "title": "beta briefing",
                "summary": "beta summary",
                "why_it_matters": "beta",
                "source_url": "https://example.test/beta",
                "status": "active",
            },
            user_id=self.user_b,
        )
        chat = self.client.post("/api/v1/chat", json={"message": "alpha"}).json()
        self.assertEqual([source["url"] for source in chat["sources"]], ["https://example.test/alpha"])

        self.selected_user = self.user_b
        b_preview = self.client.post("/api/v1/routes/preview").json()
        self.assertEqual(set(b_preview["selected_sources"]), {"github"})
        self.assertIn("beta-topic", " ".join(route["reason"] for route in b_preview["routes"]))
        self.assertEqual(self.client.get(f"/api/v1/pipeline/runs/{a_run_id}").status_code, 404)
        self.assertNotIn(a_run_id, [run["id"] for run in self.client.get("/api/v1/pipeline/runs").json()["runs"]])
        chat = self.client.post("/api/v1/chat", json={"message": "beta"}).json()
        self.assertEqual([source["url"] for source in chat["sources"]], ["https://example.test/beta"])
        self.assertEqual(self.store.get_signal(a_signal, user_id=self.user_b), None)
        self.assertIsNotNone(self.store.get_signal(b_signal, user_id=self.user_b))

    def test_default_local_user_remains_the_api_fallback(self):
        local_run = self.store.create_pipeline_run("local-run")
        self.app.dependency_overrides.pop(get_current_user)
        response = self.client.get("/api/v1/pipeline/runs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([run["id"] for run in response.json()["runs"]], [local_run])
        self.assertEqual(self.store.get_pipeline_run(local_run)["user_id"], DEFAULT_LOCAL_USER_ID)


if __name__ == "__main__":
    unittest.main()

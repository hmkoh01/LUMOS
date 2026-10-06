import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.signals.pipeline import SignalPipeline
from src.sources.collectors.base import CollectedItem, CollectorResult
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class UserPipelinePropagationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "pipeline-propagation.db")
        with self.store.connect() as conn:
            conn.execute("INSERT INTO users (external_id) VALUES ('pipeline-a')")
            conn.execute("INSERT INTO users (external_id) VALUES ('pipeline-b')")
            self.user_a = conn.execute(
                "SELECT id FROM users WHERE external_id = 'pipeline-a'"
            ).fetchone()[0]
            self.user_b = conn.execute(
                "SELECT id FROM users WHERE external_id = 'pipeline-b'"
            ).fetchone()[0]

    def configure_user(self, user_id, keyword, enabled_source):
        self.store.update_settings({"signal_count": 1}, user_id=user_id)
        self.store.upsert_profile({"role": f"{keyword} analyst"}, user_id=user_id)
        self.store.add_manual_interest(keyword, user_id=user_id)
        for config in self.store.get_source_configs(user_id=user_id):
            self.store.upsert_source_config(
                config["source_id"], enabled=config["source_id"] == enabled_source, user_id=user_id
            )

    @staticmethod
    def collect_mock_items(source, queries, limit, mode):
        keyword = {
            "hackernews": "alpha-topic",
            "github": "beta-topic",
            "rss": "local-topic",
        }[source]
        return CollectorResult(
            source=source,
            items=[
                CollectedItem(
                    source=source,
                    source_item_id=f"{keyword}-{index}",
                    url=f"https://example.test/{keyword}/{index}",
                    title=f"{keyword} update {index}",
                    summary=f"Latest {keyword} signal",
                    raw_json={"mock": True},
                )
                for index in range(2)
            ],
        )

    def test_daily_pipeline_propagates_user_scope_to_runs_signals_and_reserves(self):
        self.configure_user(self.user_a, "alpha-topic", "hackernews")
        self.configure_user(self.user_b, "beta-topic", "github")

        with patch("src.signals.pipeline.CollectorRegistry.collect", side_effect=self.collect_mock_items):
            a_result = SignalPipeline(self.store).generate_daily_signals(mode="mock", user_id=self.user_a)
            b_result = SignalPipeline(self.store).generate_daily_signals(mode="mock", user_id=self.user_b)

        a_run = self.store.get_pipeline_run(a_result["pipeline_run_id"], user_id=self.user_a)
        b_run = self.store.get_pipeline_run(b_result["pipeline_run_id"], user_id=self.user_b)
        self.assertEqual(a_run["status"], "completed")
        self.assertEqual(b_run["status"], "completed")
        self.assertIsNone(self.store.get_pipeline_run(a_result["pipeline_run_id"], user_id=self.user_b))
        self.assertIsNone(self.store.get_pipeline_run(b_result["pipeline_run_id"], user_id=self.user_a))
        self.assertEqual(a_run["selected_sources_json"], ["hackernews"])
        self.assertEqual(b_run["selected_sources_json"], ["github"])

        a_signals = self.store.get_today_active_signals(user_id=self.user_a)
        b_signals = self.store.get_today_active_signals(user_id=self.user_b)
        self.assertEqual(len(a_signals), 1)
        self.assertEqual(len(b_signals), 1)
        self.assertIn("alpha-topic", a_signals[0]["title"])
        self.assertIn("beta-topic", b_signals[0]["title"])
        self.assertEqual(a_signals[0]["user_id"], self.user_a)
        self.assertEqual(b_signals[0]["user_id"], self.user_b)
        self.assertEqual(self.store.get_today_active_signals(user_id=DEFAULT_LOCAL_USER_ID), [])

        self.assertEqual(len(self.store.get_signal_reserves(a_run["id"], user_id=self.user_a)), 1)
        self.assertEqual(len(self.store.get_signal_reserves(b_run["id"], user_id=self.user_b)), 1)
        self.assertEqual(self.store.get_signal_reserves(a_run["id"], user_id=self.user_b), [])
        self.assertEqual(self.store.get_signal_reserves(b_run["id"], user_id=self.user_a), [])

    def test_default_local_pipeline_flow_remains_available(self):
        self.configure_user(DEFAULT_LOCAL_USER_ID, "local-topic", "rss")
        with patch("src.signals.pipeline.CollectorRegistry.collect", side_effect=self.collect_mock_items):
            result = SignalPipeline(self.store).generate_daily_signals(mode="mock")

        run = self.store.get_pipeline_run(result["pipeline_run_id"])
        signals = self.store.get_today_active_signals()
        self.assertEqual(run["user_id"], DEFAULT_LOCAL_USER_ID)
        self.assertEqual(len(signals), 1)
        self.assertIn("local-topic", signals[0]["title"])
        self.assertEqual(len(self.store.get_signal_reserves(run["id"])), 1)


if __name__ == "__main__":
    unittest.main()

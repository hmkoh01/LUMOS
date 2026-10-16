import tempfile
import unittest
from pathlib import Path

from src.sources.router import SourceRouter
from src.sources.source_registry import source_availability
from src.storage.sqlite_store import SQLiteStore


class SourceSelectionTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "sources.db")
        self.store.add_manual_interest("machine learning", user_id=1)

    def plan(self, user_id=1):
        return SourceRouter().plan(
            self.store.get_profile(user_id=user_id) or {},
            self.store.get_settings(user_id=user_id),
            [],
            self.store.get_interests(limit=50, user_id=user_id),
            source_configs=self.store.get_source_configs(user_id=user_id),
        )

    def test_new_user_sources_default_to_auto(self):
        configs = self.store.get_source_configs()
        self.assertTrue(configs)
        self.assertTrue(all(config["selection_mode"] == "auto" for config in configs))
        self.assertEqual(self.store.get_settings()["source_region_preference"], "both")

    def test_disabled_source_is_never_automatically_reenabled(self):
        self.store.upsert_source_config("github", selection_mode="disabled")
        self.assertNotIn("github", {route["source"] for route in self.plan()})

    def test_manual_source_can_return_to_auto(self):
        self.store.upsert_source_config("github", selection_mode="enabled")
        self.assertEqual(self.store.get_source_config("github")["selection_mode"], "enabled")
        self.store.upsert_source_config("github", selection_mode="auto")
        self.assertEqual(self.store.get_source_config("github")["selection_mode"], "auto")

    def test_unavailable_source_is_not_collected_even_when_enabled(self):
        self.store.upsert_source_config("youtube", selection_mode="enabled")
        self.assertFalse(source_availability("youtube", {})["available"])
        self.assertNotIn("youtube", {route["source"] for route in self.plan()})

    def test_domestic_preference_is_a_priority_not_a_hard_filter(self):
        self.store.update_settings({"source_region_preference": "domestic"})
        self.assertIn("github", {route["source"] for route in self.plan()})

    def test_source_preference_is_user_scoped(self):
        with self.store.connect() as conn:
            conn.execute("INSERT INTO users (external_id) VALUES ('source-selection-user-b')")
            user_b = conn.execute("SELECT id FROM users WHERE external_id = 'source-selection-user-b'").fetchone()[0]
        self.store.upsert_source_config("github", selection_mode="disabled", user_id=1)
        self.store.upsert_source_config("github", selection_mode="enabled", user_id=user_b)
        self.store.update_settings({"source_region_preference": "domestic"}, user_id=1)
        self.store.update_settings({"source_region_preference": "international"}, user_id=user_b)
        self.assertEqual(self.store.get_source_config("github", user_id=1)["selection_mode"], "disabled")
        self.assertEqual(self.store.get_source_config("github", user_id=user_b)["selection_mode"], "enabled")
        self.assertEqual(self.store.get_settings(user_id=1)["source_region_preference"], "domestic")
        self.assertEqual(self.store.get_settings(user_id=user_b)["source_region_preference"], "international")


if __name__ == "__main__":
    unittest.main()

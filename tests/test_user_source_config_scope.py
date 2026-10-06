import tempfile
import unittest
from pathlib import Path

from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class UserSourceConfigScopeTest(unittest.TestCase):
    def test_source_configs_and_seed_are_user_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "sources.db")
            with store.connect() as conn:
                conn.execute("INSERT INTO users (external_id) VALUES ('source-a')")
                conn.execute("INSERT INTO users (external_id) VALUES ('source-b')")
                a = conn.execute("SELECT id FROM users WHERE external_id = 'source-a'").fetchone()[0]
                b = conn.execute("SELECT id FROM users WHERE external_id = 'source-b'").fetchone()[0]
            store.upsert_source_config("rss", enabled=True, priority=90, config={"feed_urls": ["a"]}, user_id=a)
            store.upsert_source_config("rss", enabled=False, priority=10, config={"feed_urls": ["b"]}, user_id=b)
            self.assertEqual(store.get_source_config("rss", user_id=a)["priority"], 90)
            self.assertEqual(store.get_source_config("rss", user_id=b)["priority"], 10)
            self.assertTrue(store.get_enabled_source_configs(user_id=a)[0]["enabled"])
            self.assertNotIn("rss", [item["source_id"] for item in store.get_enabled_source_configs(user_id=b)])
            store.seed_default_source_configs(user_id=a)
            self.assertEqual(store.get_source_config("rss", user_id=a)["priority"], 90)
            self.assertEqual(len(store.seed_default_source_configs(user_id=b)), len(store.get_source_configs(user_id=b)))
            self.assertTrue(store.get_source_configs(user_id=DEFAULT_LOCAL_USER_ID))


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class UserSettingsProfileScopeTest(unittest.TestCase):
    def test_settings_and_profiles_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "scope.db")
            with store.connect() as conn:
                conn.execute("INSERT INTO users (external_id) VALUES ('scope-a')")
                conn.execute("INSERT INTO users (external_id) VALUES ('scope-b')")
                a = conn.execute("SELECT id FROM users WHERE external_id = 'scope-a'").fetchone()[0]
                b = conn.execute("SELECT id FROM users WHERE external_id = 'scope-b'").fetchone()[0]

            store.update_settings({"signal_count": 5, "briefing_time": "07:30"}, user_id=a)
            store.update_settings({"signal_count": 1, "briefing_time": "18:00"}, user_id=b)
            self.assertEqual(store.get_settings(a)["signal_count"], 5)
            self.assertEqual(store.get_settings(b)["signal_count"], 1)
            self.assertEqual(store.get_settings(DEFAULT_LOCAL_USER_ID)["signal_count"], 3)

            store.upsert_profile({"role": "A", "goals": ["alpha"]}, user_id=a)
            store.upsert_profile({"role": "B", "goals": ["beta"]}, user_id=b)
            self.assertEqual(store.get_profile(a)["role"], "A")
            self.assertEqual(store.get_profile(b)["role"], "B")
            store.upsert_profile({"role": "A2", "goals": []}, user_id=a)
            self.assertEqual(store.get_profile(a)["role"], "A2")
            self.assertEqual(store.get_profile(b)["role"], "B")


if __name__ == "__main__":
    unittest.main()

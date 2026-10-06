import tempfile
import unittest
from pathlib import Path

from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class UserInterestScopeTest(unittest.TestCase):
    def test_interest_operations_are_user_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "interests.db")
            with store.connect() as conn:
                conn.execute("INSERT INTO users (external_id) VALUES ('interest-a')")
                conn.execute("INSERT INTO users (external_id) VALUES ('interest-b')")
                a = conn.execute("SELECT id FROM users WHERE external_id = 'interest-a'").fetchone()[0]
                b = conn.execute("SELECT id FROM users WHERE external_id = 'interest-b'").fetchone()[0]
            for user_id in (a, b):
                store.upsert_interest("AI", "manual", 1, "manual", {}, user_id=user_id)
            self.assertEqual([item["keyword"] for item in store.get_interests(user_id=a)], ["AI"])
            store.update_interest("AI", weight=8, user_id=a)
            self.assertEqual(store.get_interests(user_id=a)[0]["weight"], 8)
            self.assertEqual(store.get_interests(user_id=b)[0]["weight"], 1)
            store.mute_interest("AI", user_id=a)
            self.assertEqual(store.get_interests(user_id=a, include_muted=True)[0]["status"], "muted")
            self.assertEqual(store.get_interests(user_id=b)[0]["status"], "active")
            store.unmute_interest("AI", user_id=a)
            store.delete_interest("AI", user_id=a)
            self.assertEqual(store.get_interests(user_id=a, include_deleted=True, include_muted=True)[0]["status"], "deleted")
            self.assertEqual(store.get_interests(user_id=b)[0]["status"], "active")
            store.add_manual_interest("local")
            self.assertEqual(store.get_interests(user_id=DEFAULT_LOCAL_USER_ID)[0]["keyword"], "local")


if __name__ == "__main__":
    unittest.main()

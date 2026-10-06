import tempfile
import unittest
from pathlib import Path

from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class UserFeedbackScopeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "feedback.db")
        with self.store.connect() as conn:
            conn.execute("INSERT INTO users (external_id) VALUES ('feedback-a')")
            conn.execute("INSERT INTO users (external_id) VALUES ('feedback-b')")
            self.user_a = conn.execute("SELECT id FROM users WHERE external_id = 'feedback-a'").fetchone()[0]
            self.user_b = conn.execute("SELECT id FROM users WHERE external_id = 'feedback-b'").fetchone()[0]

    def create_signal(self, user_id, suffix):
        return self.store.create_signal({
            "title": f"article {suffix}", "summary": "summary", "why_it_matters": "why",
            "source_url": f"https://feedback.test/{suffix}", "status": "active",
            "metadata_json": {"briefing_version": 9},
        }, user_id=user_id)

    def test_feedback_isolated_by_signal_owner_and_event_owner(self):
        a_saved = self.create_signal(self.user_a, "same")
        b_saved = self.create_signal(self.user_b, "same")
        a_tracked = self.create_signal(self.user_a, "tracked")
        b_ignored = self.create_signal(self.user_b, "ignored")

        self.store.record_feedback(a_saved, "saved", user_id=self.user_a)
        with self.assertRaises(ValueError):
            self.store.record_feedback(a_saved, "saved", user_id=self.user_b)
        self.store.record_feedback(b_saved, "saved", user_id=self.user_b)
        self.store.record_feedback(a_tracked, "tracked", user_id=self.user_a)
        self.store.record_feedback(b_ignored, "ignored", user_id=self.user_b)

        self.assertEqual([item["id"] for item in self.store.get_saved_signals(user_id=self.user_a)], [a_saved])
        self.assertEqual([item["id"] for item in self.store.get_saved_signals(user_id=self.user_b)], [b_saved])
        self.assertEqual([item["id"] for item in self.store.get_feedback_signals("tracked", user_id=self.user_a)], [a_tracked])
        self.assertEqual([item["id"] for item in self.store.get_feedback_signals("ignored", user_id=self.user_b)], [b_ignored])
        self.assertFalse(self.store.has_feedback_signal(a_saved, "saved", user_id=self.user_b))
        self.assertTrue(self.store.has_feedback_signal(a_saved, "saved", user_id=self.user_a))

        self.assertTrue(self.store.clear_feedback_signal(a_tracked, "tracked", user_id=self.user_a))
        self.assertEqual(self.store.get_signal(b_ignored, user_id=self.user_b)["status"], "ignored")
        self.assertTrue(self.store.delete_saved_signal(a_saved, user_id=self.user_a))
        self.assertEqual([item["id"] for item in self.store.get_saved_signals(user_id=self.user_b)], [b_saved])
        self.assertTrue(all(event["user_id"] == self.user_a for event in self.store.get_recent_feedback_events(user_id=self.user_a)))
        self.assertTrue(all(event["user_id"] == self.user_b for event in self.store.get_recent_feedback_events(user_id=self.user_b)))

    def test_default_local_user_feedback_still_works(self):
        signal_id = self.create_signal(DEFAULT_LOCAL_USER_ID, "local")
        self.store.record_feedback(signal_id, "saved")
        self.assertEqual([item["id"] for item in self.store.get_saved_signals()], [signal_id])


if __name__ == "__main__":
    unittest.main()

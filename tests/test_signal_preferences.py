import tempfile
import unittest
from pathlib import Path

from src.context.feedback_learning import apply_feedback_learning
from src.signals.feedback import FeedbackService
from src.storage.sqlite_store import SQLiteStore


class SignalPreferencesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SQLiteStore(Path(self.tmp.name) / "preferences.db")
        self.store.add_manual_interest("agent")
        self.signal_id = self.store.create_signal({
            "title": "agent update", "summary": "agent", "why_it_matters": "agent",
            "source_name": "GitHub", "source_url": "https://example.test/agent", "status": "active",
        })
        self.service = FeedbackService(self.store)

    def test_saved_and_recommendation_preference_are_independent(self):
        self.service.set_saved(self.signal_id, True)
        self.service.set_recommendation_preference(self.signal_id, "tracked")
        self.assertEqual(self.store.get_signal_preference_state(self.signal_id)["recommendation_preference"], "tracked")
        self.service.set_saved(self.signal_id, False)
        self.assertFalse(self.store.get_signal_preference_state(self.signal_id)["saved"])
        self.assertEqual(self.store.get_signal_preference_state(self.signal_id)["recommendation_preference"], "tracked")
        self.service.set_recommendation_preference(self.signal_id, None)
        self.assertIsNone(self.store.get_signal_preference_state(self.signal_id)["recommendation_preference"])

    def test_repeated_selection_does_not_reapply_learning(self):
        before = self.store.get_interests()[0]["weight"]
        self.service.set_recommendation_preference(self.signal_id, "tracked")
        once = self.store.get_interests()[0]["weight"]
        self.service.set_recommendation_preference(self.signal_id, "tracked")
        self.assertGreater(once, before)
        self.assertEqual(self.store.get_interests()[0]["weight"], once)
        self.service.set_recommendation_preference(self.signal_id, None)
        self.assertEqual(self.store.get_interests()[0]["weight"], before)


if __name__ == "__main__":
    unittest.main()

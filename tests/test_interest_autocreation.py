import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.context.feedback_learning import apply_feedback_learning
from src.context.sync import apply_keywords_to_interest_graph
from src.storage.sqlite_store import SQLiteStore


class InterestAutocreationTest(unittest.TestCase):
    def test_automatic_interests_require_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.db"
            store = SQLiteStore(path)
            self.assertFalse(store.get_settings()["auto_expand_interests"])
            store.upsert_interest("manual-keyword", "onboarding", 1, "onboarding", {})
            before = store.get_interests(include_muted=True)
            signal = {"title": "robotics automation", "category": "technology", "source_name": "hackernews"}
            with patch.object(store, "get_signal", return_value=signal):
                for event in ("opened", "saved", "tracked", "ignored"):
                    self.assertEqual(apply_feedback_learning(store, 1, event), [])
                for connector in ("local_files", "browser_history"):
                    self.assertEqual(apply_keywords_to_interest_graph(store, connector, [{"keyword": "new-keyword", "score": 1}], []), [])
                self.assertEqual(store.get_interests(include_muted=True), before)
                store.update_settings({"auto_expand_interests": True})
                self.assertTrue(apply_feedback_learning(store, 1, "opened"))
                self.assertTrue(apply_keywords_to_interest_graph(store, "local_files", [{"keyword": "new-keyword", "score": 1}], []))
            store.update_settings({"auto_expand_interests": False})
            self.assertFalse(SQLiteStore(path).get_settings()["auto_expand_interests"])


if __name__ == "__main__":
    unittest.main()

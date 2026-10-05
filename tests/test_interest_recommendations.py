import tempfile
import unittest
from pathlib import Path

from src.api.context import RECOMMENDATION_COUNT, _interest_recommendations
from src.storage.sqlite_store import SQLiteStore


class InterestRecommendationTest(unittest.TestCase):
    def test_returns_four_recommendations_after_keywords_are_added_or_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "test.db")
            initial = _interest_recommendations(store)
            self.assertEqual(len(initial), RECOMMENDATION_COUNT)

            store.add_manual_interest(initial[0]["keyword"])
            self.assertEqual(len(_interest_recommendations(store)), RECOMMENDATION_COUNT)

            store.delete_interest(initial[0]["keyword"])
            self.assertEqual(len(_interest_recommendations(store)), RECOMMENDATION_COUNT)


if __name__ == "__main__":
    unittest.main()

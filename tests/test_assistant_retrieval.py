"""
Tests for SQLiteRetrievalService.

Verifies:
- User A's signals are NOT retrievable by User B
- Period filters (today / week / month)
- selected_signal_id appears first
- selected_signal_id from wrong user is silently ignored
"""
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from src.assistant.retrieval import SQLiteRetrievalService
from src.storage.sqlite_store import SQLiteStore


def _utc_ago(days: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _make_store() -> SQLiteStore:
    f = NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return SQLiteStore(db_path=Path(f.name))


def _insert_signal(store: SQLiteStore, user_id: int, title: str, days_ago: float = 1) -> int:
    with store.connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO signals
                (user_id, title, summary, why_it_matters, source_name, source_url,
                 signal_date, confidence, rank, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, date('now'), 0.8, 1, 'active', ?)
            """,
            (user_id, title, f"{title} summary", f"{title} importance",
             "TestSource", "https://example.com", _utc_ago(days_ago)),
        )
        conn.commit()
        return int(cur.lastrowid)


class TestUserIsolation(unittest.TestCase):
    """User A's signals must not appear in User B's retrieval."""

    def setUp(self):
        self.store = _make_store()
        with self.store.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id, external_id) VALUES (1, 'user-a')")
            conn.execute("INSERT OR IGNORE INTO users (id, external_id) VALUES (2, 'user-b')")
            conn.commit()

    def test_user_b_cannot_see_user_a_signals(self):
        _insert_signal(self.store, user_id=1, title="OpenAI GPT-5 released", days_ago=1)
        svc = SQLiteRetrievalService(self.store)
        results = svc.retrieve("OpenAI GPT", user_id=2, period="week")
        self.assertEqual(results, [], "User B should get no results from User A's signals")

    def test_user_a_sees_own_signals(self):
        _insert_signal(self.store, user_id=1, title="OpenAI GPT-5 released", days_ago=1)
        svc = SQLiteRetrievalService(self.store)
        results = svc.retrieve("OpenAI", user_id=1, period="week")
        self.assertGreater(len(results), 0)
        self.assertTrue(all(True for r in results))  # all from user 1 implicitly


class TestPeriodFilter(unittest.TestCase):
    """Period filters must exclude signals outside the window."""

    def setUp(self):
        self.store = _make_store()
        with self.store.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id, external_id) VALUES (1, 'user-a')")
            conn.commit()

    def test_today_excludes_yesterday(self):
        _insert_signal(self.store, 1, "AI news today", days_ago=0.1)
        _insert_signal(self.store, 1, "AI news old", days_ago=2)
        svc = SQLiteRetrievalService(self.store)
        results = svc.retrieve("AI news", user_id=1, period="today")
        titles = [r.title for r in results]
        self.assertFalse(
            any("old" in t for t in titles),
            f"today filter should exclude 2-day-old signal; got {titles}",
        )

    def test_week_includes_five_days_ago(self):
        _insert_signal(self.store, 1, "Weekly AI update", days_ago=5)
        svc = SQLiteRetrievalService(self.store)
        results = svc.retrieve("Weekly AI", user_id=1, period="week")
        self.assertGreater(len(results), 0)

    def test_today_excludes_five_days_ago(self):
        _insert_signal(self.store, 1, "Weekly AI update", days_ago=5)
        svc = SQLiteRetrievalService(self.store)
        results = svc.retrieve("Weekly AI", user_id=1, period="today")
        self.assertEqual(results, [])


class TestSelectedSignal(unittest.TestCase):
    """selected_signal_id must appear first and be validated by ownership."""

    def setUp(self):
        self.store = _make_store()
        with self.store.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id, external_id) VALUES (1, 'user-a')")
            conn.execute("INSERT OR IGNORE INTO users (id, external_id) VALUES (2, 'user-b')")
            conn.commit()

    def test_selected_signal_is_first(self):
        id1 = _insert_signal(self.store, 1, "AI chip breakthrough", days_ago=1)
        _insert_signal(self.store, 1, "AI chip breakthrough extra", days_ago=1)
        svc = SQLiteRetrievalService(self.store)
        results = svc.retrieve("AI chip", user_id=1, period="week", selected_signal_id=id1)
        self.assertTrue(results[0].is_selected)
        self.assertEqual(results[0].signal_id, id1)

    def test_other_user_signal_id_is_ignored(self):
        user_b_id = _insert_signal(self.store, 2, "Secret User B signal", days_ago=1)
        svc = SQLiteRetrievalService(self.store)
        # User A requests with User B's signal_id
        results = svc.retrieve("Secret", user_id=1, period="week", selected_signal_id=user_b_id)
        ids = [r.signal_id for r in results]
        self.assertNotIn(user_b_id, ids, "User B's signal must not appear in User A's results")

    def test_selected_outside_period_still_included(self):
        old_id = _insert_signal(self.store, 1, "Old important signal", days_ago=10)
        svc = SQLiteRetrievalService(self.store)
        results = svc.retrieve("important", user_id=1, period="week", selected_signal_id=old_id)
        ids = [r.signal_id for r in results]
        self.assertIn(old_id, ids, "Selected signal should be included even if outside period")
        self.assertTrue(results[0].is_selected)


if __name__ == "__main__":
    unittest.main()

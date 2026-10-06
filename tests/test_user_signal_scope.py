import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class UserSignalScopeTest(unittest.TestCase):
    def test_signal_queries_are_user_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "signals.db")
            with store.connect() as conn:
                conn.execute("INSERT INTO users (external_id) VALUES ('signal-a')")
                conn.execute("INSERT INTO users (external_id) VALUES ('signal-b')")
                a = conn.execute("SELECT id FROM users WHERE external_id = 'signal-a'").fetchone()[0]
                b = conn.execute("SELECT id FROM users WHERE external_id = 'signal-b'").fetchone()[0]
            signal = {"title": "same article", "summary": "x", "why_it_matters": "x", "source_url": "https://example.test/a", "status": "active", "metadata_json": {"briefing_version": 9, "published_at": "2026-10-06T10:00:00Z"}}
            a_id = store.create_signal(signal, user_id=a)
            b_id = store.create_signal(signal, user_id=b)
            reference = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
            self.assertEqual([item["id"] for item in store.get_today_signals(user_id=a)], [a_id])
            self.assertEqual([item["id"] for item in store.get_signals_for_period("week", now=reference, user_id=b)], [b_id])
            self.assertIsNone(store.get_signal(a_id, user_id=b))
            self.assertEqual(store.get_today_signals(user_id=DEFAULT_LOCAL_USER_ID), [])


if __name__ == "__main__":
    unittest.main()

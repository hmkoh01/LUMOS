import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class UserContextScopeTest(unittest.TestCase):
    def test_context_items_and_sync_runs_are_user_scoped_and_migrate_legacy_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy-context.db"
            with sqlite3.connect(path) as conn:
                conn.execute(
                    """
                    CREATE TABLE context_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        connector_type TEXT NOT NULL, item_id TEXT NOT NULL, dedupe_key TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL DEFAULT '', text_snippet TEXT NOT NULL DEFAULT '', url TEXT, path TEXT,
                        metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT, updated_at TEXT,
                        collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE context_sync_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, connector_type TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'running', started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        completed_at TEXT, item_count INTEGER NOT NULL DEFAULT 0, keyword_count INTEGER NOT NULL DEFAULT 0,
                        summary_json TEXT NOT NULL DEFAULT '{}', error_message TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO context_items (connector_type, item_id, dedupe_key, title, text_snippet, path)
                    VALUES ('local_files', 'legacy-1', 'same-key', 'Legacy note', 'legacy private snippet', 'C:/legacy/private.txt')
                    """
                )
                conn.execute(
                    "INSERT INTO context_sync_runs (connector_type, status, item_count) VALUES ('local_files', 'completed', 3)"
                )

            store = SQLiteStore(path)
            legacy = store.get_context_items()
            self.assertEqual(len(legacy), 1)
            self.assertEqual(legacy[0]["user_id"], DEFAULT_LOCAL_USER_ID)
            self.assertEqual(legacy[0]["text_snippet"], "legacy private snippet")
            self.assertEqual(store.get_recent_context_sync_runs()[0]["user_id"], DEFAULT_LOCAL_USER_ID)

            with store.connect() as conn:
                conn.execute("INSERT INTO users (external_id) VALUES ('context-a')")
                conn.execute("INSERT INTO users (external_id) VALUES ('context-b')")
                user_a = conn.execute("SELECT id FROM users WHERE external_id = 'context-a'").fetchone()[0]
                user_b = conn.execute("SELECT id FROM users WHERE external_id = 'context-b'").fetchone()[0]

            a_id = store.upsert_context_item(
                {
                    "connector_type": "local_files", "item_id": "same", "dedupe_key": "same-key",
                    "title": "A private file", "text_snippet": "A secret snippet", "path": "C:/a/secret.txt",
                },
                user_id=user_a,
            )
            b_id = store.upsert_context_item(
                {
                    "connector_type": "local_files", "item_id": "same", "dedupe_key": "same-key",
                    "title": "B private file", "text_snippet": "B secret snippet", "path": "C:/b/secret.txt",
                },
                user_id=user_b,
            )
            self.assertNotEqual(a_id, b_id)
            self.assertEqual([item["text_snippet"] for item in store.get_context_items(user_id=user_a)], ["A secret snippet"])
            self.assertEqual([item["path"] for item in store.get_context_items(user_id=user_b, search="secret")], ["C:/b/secret.txt"])
            self.assertFalse(store.delete_context_item(a_id, user_id=user_b))
            self.assertTrue(store.delete_context_item(a_id, user_id=user_a))
            self.assertEqual([item["id"] for item in store.get_context_items(user_id=user_b)], [b_id])

            a_run = store.create_context_sync_run("local_files", user_id=user_a)
            b_run = store.create_context_sync_run("local_files", user_id=user_b)
            self.assertFalse(store.complete_context_sync_run(a_run, item_count=9, user_id=user_b))
            self.assertTrue(store.complete_context_sync_run(a_run, item_count=2, user_id=user_a))
            self.assertEqual(store.get_context_sync_run(a_run, user_id=user_b), None)
            self.assertEqual(store.get_context_sync_run(a_run, user_id=user_a)["item_count"], 2)
            self.assertEqual([run["id"] for run in store.get_recent_context_sync_runs(user_id=user_b)], [b_run])


if __name__ == "__main__":
    unittest.main()

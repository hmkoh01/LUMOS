import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.storage.sqlite_store import SQLiteStore


class UserSchemaMigrationTest(unittest.TestCase):
    def test_fresh_schema_supports_per_user_interest_and_source_config_uniqueness(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "users.db")
            with store.connect() as conn:
                conn.execute("INSERT INTO users (external_id) VALUES ('user-a')")
                conn.execute("INSERT INTO users (external_id) VALUES ('user-b')")
                a = conn.execute("SELECT id FROM users WHERE external_id = 'user-a'").fetchone()[0]
                b = conn.execute("SELECT id FROM users WHERE external_id = 'user-b'").fetchone()[0]
                for user_id in (a, b):
                    conn.execute("INSERT INTO interest_graph (user_id, keyword, category, source) VALUES (?, 'AI', 'manual', 'manual')", (user_id,))
                    conn.execute("INSERT INTO source_configs (user_id, source_id) VALUES (?, 'rss')", (user_id,))
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute("INSERT INTO interest_graph (user_id, keyword, category, source) VALUES (?, 'AI', 'manual', 'manual')", (a,))
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute("INSERT INTO source_configs (user_id, source_id) VALUES (?, 'rss')", (a,))


if __name__ == "__main__":
    unittest.main()

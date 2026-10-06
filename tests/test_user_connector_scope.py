import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class UserConnectorScopeTest(unittest.TestCase):
    def test_legacy_connectors_migrate_to_local_user_and_users_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy-connectors.db"
            with sqlite3.connect(path) as conn:
                conn.execute(
                    """
                    CREATE TABLE connectors (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        connector_type TEXT NOT NULL UNIQUE,
                        enabled INTEGER NOT NULL DEFAULT 0,
                        auth_status TEXT NOT NULL DEFAULT 'not_connected',
                        config_json TEXT NOT NULL DEFAULT '{}',
                        last_sync_at TEXT,
                        last_status TEXT,
                        last_error TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO connectors (connector_type, enabled, auth_status, config_json, last_status)
                    VALUES ('browser_history', 1, 'connected', '{"profile":"legacy"}', 'ok')
                    """
                )

            store = SQLiteStore(path)
            legacy = store.get_connector("browser_history")
            self.assertEqual(legacy["user_id"], DEFAULT_LOCAL_USER_ID)
            self.assertTrue(legacy["enabled"])
            self.assertEqual(legacy["auth_status"], "connected")
            self.assertEqual(legacy["config_json"], {"profile": "legacy"})
            self.assertEqual(legacy["last_status"], "ok")

            with store.connect() as conn:
                conn.execute("INSERT INTO users (external_id) VALUES ('connector-a')")
                conn.execute("INSERT INTO users (external_id) VALUES ('connector-b')")
                user_a = conn.execute("SELECT id FROM users WHERE external_id = 'connector-a'").fetchone()[0]
                user_b = conn.execute("SELECT id FROM users WHERE external_id = 'connector-b'").fetchone()[0]

            store.update_connector("browser_history", True, {"profile": "a"}, user_id=user_a)
            store.update_connector("browser_history", False, {"profile": "b"}, user_id=user_b)
            self.assertEqual(store.get_connector("browser_history", user_id=user_a)["config_json"], {"profile": "a"})
            self.assertEqual(store.get_connector("browser_history", user_id=user_b)["config_json"], {"profile": "b"})
            self.assertTrue(store.get_connector("browser_history", user_id=user_a)["enabled"])
            self.assertFalse(store.get_connector("browser_history", user_id=user_b)["enabled"])
            self.assertEqual(store.get_settings(user_id=user_a)["enabled_connectors_json"]["browser_history"], True)
            self.assertEqual(store.get_settings(user_id=user_b)["enabled_connectors_json"]["browser_history"], False)
            self.assertEqual(store.get_connector("browser_history")["config_json"], {"profile": "legacy"})


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class UserPipelineRunScopeTest(unittest.TestCase):
    def test_runs_are_user_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "runs.db")
            with store.connect() as conn:
                conn.execute("INSERT INTO users (external_id) VALUES ('run-a')")
                conn.execute("INSERT INTO users (external_id) VALUES ('run-b')")
                a = conn.execute("SELECT id FROM users WHERE external_id = 'run-a'").fetchone()[0]
                b = conn.execute("SELECT id FROM users WHERE external_id = 'run-b'").fetchone()[0]
            a_run = store.create_pipeline_run("test", user_id=a)
            b_run = store.create_pipeline_run("test", user_id=b)
            self.assertEqual([run["id"] for run in store.get_recent_pipeline_runs(user_id=a)], [a_run])
            self.assertIsNone(store.get_pipeline_run(a_run, user_id=b))
            store.complete_pipeline_run(a_run, {"selected_sources": []}, user_id=b)
            self.assertEqual(store.get_pipeline_run(a_run, user_id=a)["status"], "running")
            store.complete_pipeline_run(a_run, {"selected_sources": []}, user_id=a)
            self.assertEqual(store.get_pipeline_run(a_run, user_id=a)["status"], "completed")
            store.fail_pipeline_run(b_run, "failed", user_id=a)
            self.assertEqual(store.get_pipeline_run(b_run, user_id=b)["status"], "running")
            local_run = store.create_pipeline_run("local")
            self.assertEqual(store.get_pipeline_run(local_run, user_id=DEFAULT_LOCAL_USER_ID)["id"], local_run)


if __name__ == "__main__":
    unittest.main()

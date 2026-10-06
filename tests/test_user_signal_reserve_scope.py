import tempfile
import unittest
from pathlib import Path

from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


class UserSignalReserveScopeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "reserves.db")
        with self.store.connect() as conn:
            conn.execute("INSERT INTO users (external_id) VALUES ('reserve-a')")
            conn.execute("INSERT INTO users (external_id) VALUES ('reserve-b')")
            self.user_a = conn.execute(
                "SELECT id FROM users WHERE external_id = 'reserve-a'"
            ).fetchone()[0]
            self.user_b = conn.execute(
                "SELECT id FROM users WHERE external_id = 'reserve-b'"
            ).fetchone()[0]

    @staticmethod
    def candidate(url, title="Reserved article"):
        return {"title": title, "url": url, "source": "rss"}

    @staticmethod
    def prepared_signal(url, title="Reserved article"):
        return {
            "title": title,
            "summary": "Summary",
            "why_it_matters": "Why it matters",
            "source_url": url,
            "source_name": "RSS",
            "status": "new",
        }

    def create_expandable_run(self, user_id, url, title="Reserved article"):
        run_id = self.store.create_pipeline_run("signal_generation", user_id=user_id)
        self.store.create_signal(
            self.prepared_signal(f"{url}/primary", f"{title} primary"),
            pipeline_run_id=run_id,
            user_id=user_id,
        )
        self.store.save_signal_reserves(run_id, [self.candidate(url, title)], 3, user_id=user_id)
        return run_id

    def test_reserves_reveals_and_expansion_status_are_user_scoped(self):
        shared_url = "https://example.test/shared-article"
        a_run = self.create_expandable_run(self.user_a, shared_url, "A article")
        b_run = self.create_expandable_run(self.user_b, shared_url, "B article")

        self.assertEqual(
            self.store.get_signal_reserves(a_run, user_id=self.user_a),
            [(4, self.candidate(shared_url, "A article"))],
        )
        self.assertEqual(self.store.get_signal_reserves(a_run, user_id=self.user_b), [])
        self.assertEqual(self.store.get_signal_reserves(b_run, user_id=self.user_a), [])
        with self.assertRaises(ValueError):
            self.store.save_signal_reserves(a_run, [self.candidate("https://example.test/blocked")], 4, user_id=self.user_b)
        with self.assertRaises(ValueError):
            self.store.reveal_signals(
                a_run,
                [(4, self.prepared_signal(shared_url, "A article"))],
                user_id=self.user_b,
            )

        self.assertEqual(self.store.signal_expansion_status(user_id=self.user_a)["pipeline_run_id"], a_run)
        self.assertEqual(self.store.signal_expansion_status(user_id=self.user_b)["pipeline_run_id"], b_run)

        self.store.reveal_signals(
            a_run,
            [(4, self.prepared_signal(shared_url, "A article"))],
            user_id=self.user_a,
        )
        self.assertEqual(self.store.get_signal_reserves(a_run, user_id=self.user_a), [])
        self.assertEqual(
            self.store.get_signal_reserves(b_run, user_id=self.user_b),
            [(4, self.candidate(shared_url, "B article"))],
        )
        self.assertEqual(
            {signal["source_url"] for signal in self.store.get_today_signals(user_id=self.user_a)},
            {f"{shared_url}/primary", shared_url},
        )
        self.assertEqual(
            [signal["source_url"] for signal in self.store.get_today_signals(user_id=self.user_b)],
            [f"{shared_url}/primary"],
        )

        self.store.reveal_signals(
            b_run,
            [(4, self.prepared_signal(shared_url, "B article"))],
            user_id=self.user_b,
        )
        self.assertEqual(
            {signal["source_url"] for signal in self.store.get_today_signals(user_id=self.user_b)},
            {f"{shared_url}/primary", shared_url},
        )

    def test_stale_run_and_default_local_reserves_remain_user_scoped(self):
        a_old_run = self.create_expandable_run(self.user_a, "https://example.test/a-old")
        b_run = self.create_expandable_run(self.user_b, "https://example.test/b-current")
        a_new_run = self.store.create_pipeline_run("signal_generation", user_id=self.user_a)
        self.store.create_signal(
            self.prepared_signal("https://example.test/a-new", "A new article"),
            pipeline_run_id=a_new_run,
            user_id=self.user_a,
        )

        self.assertEqual(self.store.signal_expansion_status(user_id=self.user_a)["pipeline_run_id"], a_new_run)
        self.assertEqual(self.store.signal_expansion_status(user_id=self.user_b)["pipeline_run_id"], b_run)
        with self.assertRaises(ValueError):
            self.store.reveal_signals(
                a_old_run,
                [(4, self.prepared_signal("https://example.test/a-old"))],
                user_id=self.user_a,
            )
        self.store.reveal_signals(
            b_run,
            [(4, self.prepared_signal("https://example.test/b-current"))],
            user_id=self.user_b,
        )

        local_run = self.create_expandable_run(
            DEFAULT_LOCAL_USER_ID,
            "https://example.test/local-reserve",
            "Local article",
        )
        self.assertEqual(
            self.store.get_signal_reserves(local_run),
            [(4, self.candidate("https://example.test/local-reserve", "Local article"))],
        )
        self.store.reveal_signals(
            local_run,
            [(4, self.prepared_signal("https://example.test/local-reserve", "Local article"))],
        )
        self.assertFalse(self.store.signal_expansion_status()["has_more"])


if __name__ == "__main__":
    unittest.main()

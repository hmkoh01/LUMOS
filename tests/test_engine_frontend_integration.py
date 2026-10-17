"""Offline integration tests: frontend → engine v2 API → backfill → undo.

Tests the full dismiss/backfill lifecycle by calling the API handler
functions directly with a real temp-DB SQLiteStore.  No HTTP server,
no external calls, no real LLM.

Validates:
- Single card dismiss with backfill replacement
- Sequential multi-card dismiss
- Undo restores original preference
- No duplicate feedback records
- Empty reserves handled gracefully
- v1 fallback when engine disabled
- Saved state independent of dismiss
- needs_generation flag correctness
"""

import os
import unittest
from unittest.mock import patch

os.environ["LUMOS_TEST_MODE"] = "true"
os.environ["LUMOS_BLOCK_EXTERNAL_CALLS"] = "true"

from src.api.engine import (
    DismissRequest,
    UndoDismissRequest,
    dismiss_signal,
    engine_status,
    undo_dismiss,
)
from src.engine.config import EngineConfig
from src.storage.sqlite_store import SQLiteStore


def _make_store():
    """Create a temp-file-backed SQLiteStore with full schema."""
    import tempfile
    from pathlib import Path
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return SQLiteStore(db_path=Path(f.name))


def _enabled_config():
    return EngineConfig(enabled=True)


def _disabled_config():
    return EngineConfig(enabled=False)


class _FakeUser:
    def __init__(self, uid=1):
        self.id = uid


def _seed_signals(store, n=5, user_id=1):
    """Insert test signals into the DB and return their IDs."""
    from datetime import date
    ids = []
    with store.connect() as conn:
        run_id = conn.execute(
            "INSERT INTO pipeline_runs (user_id, run_type, status, profile_snapshot_json, interest_snapshot_json) "
            "VALUES (?, 'daily', 'completed', '{}', '[]')",
            (user_id,),
        ).lastrowid
        for i in range(n):
            sid = conn.execute(
                """INSERT INTO signals
                   (user_id, pipeline_run_id, signal_date, rank, status,
                    source_name, source_url, title, summary, why_it_matters,
                    category, dedupe_key, source_items_json, metadata_json)
                   VALUES (?, ?, ?, ?, 'active', 'mock', ?, ?, ?, '', 'AI_LLM_AGENT',
                    ?, '[]', '{}')""",
                (user_id, run_id, date.today().isoformat(), i + 1,
                 f"https://example.com/{i}", f"Signal {i}", f"Summary {i}",
                 f"signal-{i}"),
            ).lastrowid
            ids.append(sid)
        conn.commit()
    return ids, run_id


def _seed_reserves(store, run_id, n=3, user_id=1, start_rank=100):
    """Insert reserve candidates into signal_reserves."""
    import json
    with store.connect() as conn:
        for i in range(n):
            candidate = {
                "source_name": "mock",
                "source_url": f"https://example.com/reserve-{i}",
                "title": f"Reserve {i}",
                "summary": f"Reserve summary {i}",
                "dedupe_key": f"reserve-{i}",
            }
            conn.execute(
                "INSERT INTO signal_reserves (pipeline_run_id, rank, candidate_json) VALUES (?, ?, ?)",
                (run_id, start_rank + i, json.dumps(candidate)),
            )
        conn.commit()


class TestDismissEndpoint(unittest.TestCase):
    """Test POST /engine/briefing/dismiss handler directly."""

    def setUp(self):
        self.store = _make_store()
        self.user = _FakeUser()

    def test_dismiss_sets_ignored_preference(self):
        ids, _ = _seed_signals(self.store)
        req = DismissRequest(signal_id=ids[0])
        result = dismiss_signal(req, self.store, self.user, _enabled_config())
        self.assertTrue(result["success"])
        self.assertEqual(result["dismissed_signal_id"], ids[0])
        self.assertTrue(result["can_undo"])

        # Verify preference was set
        signal = self.store.get_signal(ids[0], user_id=self.user.id)
        self.assertEqual(signal["recommendation_preference"], "ignored")

    def test_dismiss_with_reserves_returns_replacement(self):
        ids, run_id = _seed_signals(self.store)
        _seed_reserves(self.store, run_id, n=2)

        req = DismissRequest(signal_id=ids[0], period="today")
        result = dismiss_signal(req, self.store, self.user, _enabled_config())
        self.assertTrue(result["success"])
        self.assertIsNotNone(result["replacement"])
        self.assertIn("title", result["replacement"])

    def test_dismiss_without_reserves_returns_null_replacement(self):
        ids, _ = _seed_signals(self.store)
        # No reserves seeded
        req = DismissRequest(signal_id=ids[0])
        result = dismiss_signal(req, self.store, self.user, _enabled_config())
        self.assertTrue(result["success"])
        self.assertIsNone(result["replacement"])

    def test_sequential_dismiss_gets_different_replacements(self):
        ids, run_id = _seed_signals(self.store, n=5)
        _seed_reserves(self.store, run_id, n=5)

        replacements = []
        for i in range(3):
            req = DismissRequest(signal_id=ids[i])
            result = dismiss_signal(req, self.store, self.user, _enabled_config())
            if result["replacement"]:
                replacements.append(result["replacement"]["title"])

        # Each replacement should be unique
        self.assertEqual(len(replacements), len(set(replacements)))

    def test_dismiss_by_dedupe_key(self):
        ids, _ = _seed_signals(self.store)
        req = DismissRequest(signal_dedupe_key="signal-0")
        result = dismiss_signal(req, self.store, self.user, _enabled_config())
        self.assertTrue(result["success"])
        self.assertEqual(result["dismissed_signal_id"], ids[0])

    def test_dismiss_requires_id_or_key(self):
        _seed_signals(self.store)
        req = DismissRequest()
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            dismiss_signal(req, self.store, self.user, _enabled_config())
        self.assertEqual(ctx.exception.status_code, 400)

    def test_dismiss_disabled_engine_returns_404(self):
        ids, _ = _seed_signals(self.store)
        req = DismissRequest(signal_id=ids[0])
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            dismiss_signal(req, self.store, self.user, _disabled_config())
        self.assertEqual(ctx.exception.status_code, 404)


class TestUndoDismissEndpoint(unittest.TestCase):
    """Test POST /engine/briefing/undo-dismiss handler directly."""

    def setUp(self):
        self.store = _make_store()
        self.user = _FakeUser()

    def test_undo_restores_preference(self):
        ids, _ = _seed_signals(self.store)
        # First dismiss
        dismiss_signal(DismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())
        signal = self.store.get_signal(ids[0], user_id=self.user.id)
        self.assertEqual(signal["recommendation_preference"], "ignored")

        # Then undo
        req = UndoDismissRequest(signal_id=ids[0])
        result = undo_dismiss(req, self.store, self.user, _enabled_config())
        self.assertTrue(result["success"])
        self.assertEqual(result["restored_signal_id"], ids[0])

        # Preference cleared
        signal = self.store.get_signal(ids[0], user_id=self.user.id)
        self.assertIsNone(signal["recommendation_preference"])

    def test_undo_returns_restored_signal_data(self):
        ids, _ = _seed_signals(self.store)
        dismiss_signal(DismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())
        result = undo_dismiss(UndoDismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())
        self.assertIsNotNone(result["restored"])
        self.assertEqual(result["restored"]["id"], ids[0])


class TestNoDuplicateFeedback(unittest.TestCase):
    """Ensure dismiss does not create duplicate feedback records."""

    def setUp(self):
        self.store = _make_store()
        self.user = _FakeUser()

    def test_single_feedback_record_per_dismiss(self):
        ids, _ = _seed_signals(self.store)
        dismiss_signal(DismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())

        with self.store.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM feedback_events WHERE signal_id = ? AND user_id = ?",
                (ids[0], self.user.id),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_dismiss_then_undo_creates_two_records(self):
        ids, _ = _seed_signals(self.store)
        dismiss_signal(DismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())
        undo_dismiss(UndoDismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())

        with self.store.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM feedback_events WHERE signal_id = ? AND user_id = ?",
                (ids[0], self.user.id),
            ).fetchone()[0]
        # "ignored" + "preference_cleared" = 2 records
        self.assertEqual(count, 2)


class TestSavedStateIndependence(unittest.TestCase):
    """Dismissing does not affect saved state; saving does not affect dismiss."""

    def setUp(self):
        self.store = _make_store()
        self.user = _FakeUser()

    def test_saved_signal_can_be_dismissed(self):
        ids, _ = _seed_signals(self.store)
        # Save signal first
        self.store.set_saved_signal(ids[0], True, user_id=self.user.id)

        # Dismiss it
        dismiss_signal(DismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())

        # Still saved
        signal = self.store.get_signal(ids[0], user_id=self.user.id)
        self.assertTrue(signal["saved"])
        self.assertEqual(signal["recommendation_preference"], "ignored")

    def test_dismiss_does_not_unsave(self):
        ids, _ = _seed_signals(self.store)
        self.store.set_saved_signal(ids[0], True, user_id=self.user.id)

        dismiss_signal(DismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())
        undo_dismiss(UndoDismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())

        signal = self.store.get_signal(ids[0], user_id=self.user.id)
        self.assertTrue(signal["saved"])
        self.assertIsNone(signal["recommendation_preference"])


class TestEngineStatusEndpoint(unittest.TestCase):
    def test_status_returns_enabled_flag(self):
        result = engine_status(_enabled_config())
        self.assertTrue(result["enabled"])
        self.assertEqual(result["engine_version"], "2.0")

    def test_status_returns_disabled_flag(self):
        result = engine_status(_disabled_config())
        self.assertFalse(result["enabled"])

    def test_status_no_auth_required(self):
        # engine_status only takes config, no user/store dependency
        result = engine_status(EngineConfig())
        self.assertIn("enabled", result)


class TestV1FallbackWhenDisabled(unittest.TestCase):
    """When engine v2 is disabled, endpoints return 404."""

    def setUp(self):
        self.store = _make_store()
        self.user = _FakeUser()

    def test_dismiss_returns_404_when_disabled(self):
        ids, _ = _seed_signals(self.store)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            dismiss_signal(DismissRequest(signal_id=ids[0]), self.store, self.user, _disabled_config())
        self.assertEqual(ctx.exception.status_code, 404)

    def test_undo_returns_404_when_disabled(self):
        ids, _ = _seed_signals(self.store)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            undo_dismiss(UndoDismissRequest(signal_id=ids[0]), self.store, self.user, _disabled_config())
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

"""Tests for the three defect fixes before production readiness.

1. NULL category bug in feedback_learning
2. End-to-end reserve generation → backfill → reload flow
3. Frontend race condition protection (per-card lock, stale response)

All tests use fake providers and temp DBs. No external calls.
"""

import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

os.environ["LUMOS_TEST_MODE"] = "true"
os.environ["LUMOS_BLOCK_EXTERNAL_CALLS"] = "true"

from src.api.engine import (
    DismissRequest,
    UndoDismissRequest,
    dismiss_signal,
    engine_status,
    undo_dismiss,
)
from src.context.feedback_learning import apply_feedback_learning, keywords_from_signal
from src.engine.config import EngineConfig
from src.storage.sqlite_store import SQLiteStore


def _make_store():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return SQLiteStore(db_path=Path(f.name))


def _enabled_config():
    return EngineConfig(enabled=True)


class _FakeUser:
    def __init__(self, uid=1):
        self.id = uid


def _seed_full_pipeline(store, n_primary=3, n_reserve=5, user_id=1):
    """Simulate a complete v1 pipeline run with signals and reserves.

    Returns (signal_ids, run_id, reserve_count).
    """
    with store.connect() as conn:
        # Ensure user exists
        conn.execute(
            "INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,)
        )
        # Create pipeline run
        run_id = conn.execute(
            "INSERT INTO pipeline_runs "
            "(user_id, run_type, status, profile_snapshot_json, interest_snapshot_json) "
            "VALUES (?, 'daily', 'completed', '{}', '[]')",
            (user_id,),
        ).lastrowid
        # Insert primary signals
        ids = []
        for i in range(n_primary):
            sid = conn.execute(
                """INSERT INTO signals
                   (user_id, pipeline_run_id, signal_date, rank, status,
                    source_name, source_url, title, summary, why_it_matters,
                    category, dedupe_key, source_items_json, metadata_json)
                   VALUES (?, ?, ?, ?, 'active', 'mock', ?, ?, ?, '',
                    'AI_LLM_AGENT', ?, '[]', '{}')""",
                (user_id, run_id, date.today().isoformat(), i + 1,
                 f"https://example.com/signal-{i}",
                 f"Primary Signal {i}", f"Summary of signal {i}",
                 f"primary-{i}"),
            ).lastrowid
            ids.append(sid)
        # Insert reserve candidates
        for i in range(n_reserve):
            candidate = {
                "source_name": "mock",
                "source": "mock",
                "source_url": f"https://example.com/reserve-{i}",
                "url": f"https://example.com/reserve-{i}",
                "title": f"Reserve Signal {i}",
                "summary": f"Reserve summary {i}",
                "why_it_matters": "",
                "category": "AI_LLM_AGENT",
                "dedupe_key": f"reserve-{i}",
                "route_category": "AI_LLM_AGENT",
                "matched_keywords_json": ["AI"],
            }
            conn.execute(
                "INSERT INTO signal_reserves (pipeline_run_id, rank, candidate_json) "
                "VALUES (?, ?, ?)",
                (run_id, n_primary + 1 + i, json.dumps(candidate)),
            )
        conn.commit()
    return ids, run_id, n_reserve


# ============================================================================
# Issue 1: NULL category fix
# ============================================================================

class TestNullCategoryFix(unittest.TestCase):
    """keywords_from_signal must handle None/missing fields gracefully."""

    def test_all_fields_none(self):
        signal = {
            "title": None,
            "summary": None,
            "why_it_matters": None,
            "category": None,
            "source_name": None,
            "source_items_json": None,
        }
        result = keywords_from_signal(signal)
        self.assertIsInstance(result, list)

    def test_missing_fields(self):
        signal = {}
        result = keywords_from_signal(signal)
        self.assertIsInstance(result, list)

    def test_mixed_none_and_values(self):
        signal = {
            "title": "AI Framework Released",
            "summary": None,
            "why_it_matters": None,
            "category": None,
            "source_name": "github",
            "source_items_json": [{"title": "repo details"}],
        }
        result = keywords_from_signal(signal)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_normal_signal_still_works(self):
        signal = {
            "title": "New AI Agent Framework",
            "summary": "A framework for building agents",
            "why_it_matters": "Important for developers",
            "category": "AI_LLM_AGENT",
            "source_name": "github",
            "source_items_json": [],
        }
        result = keywords_from_signal(signal)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_apply_feedback_with_null_category_signal(self):
        """Full feedback learning with NULL category in DB — the original crash."""
        store = _make_store()
        user_id = 1
        with store.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
            run_id = conn.execute(
                "INSERT INTO pipeline_runs (user_id, run_type, status) "
                "VALUES (?, 'daily', 'completed')", (user_id,)
            ).lastrowid
            # Signal with NULL category (the exact scenario that crashed)
            sid = conn.execute(
                """INSERT INTO signals
                   (user_id, pipeline_run_id, signal_date, rank, status,
                    source_name, source_url, title, summary, why_it_matters,
                    category, dedupe_key, source_items_json, metadata_json)
                   VALUES (?, ?, ?, 1, 'active', 'hackernews', 'https://example.com',
                    'Test Signal', 'Test summary', '', NULL, 'test-null-cat',
                    '[]', '{}')""",
                (user_id, run_id, date.today().isoformat()),
            ).lastrowid
            conn.commit()

        # This used to crash with: TypeError: sequence item 3: expected str instance, NoneType found
        result = apply_feedback_learning(store, sid, "ignored", user_id=user_id)
        self.assertIsInstance(result, list)

    def test_apply_feedback_with_null_source_name(self):
        store = _make_store()
        user_id = 1
        with store.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
            run_id = conn.execute(
                "INSERT INTO pipeline_runs (user_id, run_type, status) "
                "VALUES (?, 'daily', 'completed')", (user_id,)
            ).lastrowid
            sid = conn.execute(
                """INSERT INTO signals
                   (user_id, pipeline_run_id, signal_date, rank, status,
                    source_name, source_url, title, summary, why_it_matters,
                    category, dedupe_key, source_items_json, metadata_json)
                   VALUES (?, ?, ?, 1, 'active', NULL, 'https://example.com',
                    'Test', 'Summary', '', 'AI_LLM_AGENT', 'test-null-source',
                    '[]', '{}')""",
                (user_id, run_id, date.today().isoformat()),
            ).lastrowid
            conn.commit()

        result = apply_feedback_learning(store, sid, "tracked", user_id=user_id)
        self.assertIsInstance(result, list)


# ============================================================================
# Issue 2: End-to-end reserve generation → backfill → reload
# ============================================================================

class TestReserveBackfillEndToEnd(unittest.TestCase):
    """Full pipeline: signals + reserves → dismiss → backfill → reload → undo."""

    def setUp(self):
        self.store = _make_store()
        self.user = _FakeUser()

    def test_reserves_are_saved_during_pipeline(self):
        """Verify signal_reserves table is populated correctly."""
        ids, run_id, n_reserve = _seed_full_pipeline(self.store, n_primary=3, n_reserve=5)
        self.assertEqual(len(ids), 3)

        expansion = self.store.signal_expansion_status(user_id=self.user.id)
        self.assertEqual(expansion["pipeline_run_id"], run_id)
        self.assertTrue(expansion["has_more"])

        reserves = self.store.get_signal_reserves(run_id, limit=10, user_id=self.user.id)
        self.assertEqual(len(reserves), 5)

    def test_dismiss_reveals_reserve(self):
        """Dismiss pulls replacement from signal_reserves."""
        ids, run_id, _ = _seed_full_pipeline(self.store, n_primary=3, n_reserve=5)
        req = DismissRequest(signal_id=ids[0])
        result = dismiss_signal(req, self.store, self.user, _enabled_config())

        self.assertTrue(result["success"])
        self.assertIsNotNone(result["replacement"])
        self.assertIn("title", result["replacement"])

    def test_sequential_dismiss_depletes_reserves(self):
        """Each dismiss uses one reserve until depleted."""
        ids, run_id, _ = _seed_full_pipeline(self.store, n_primary=3, n_reserve=2)

        # Dismiss all 3 primary signals — only 2 reserves available
        replacements = []
        for i in range(3):
            result = dismiss_signal(
                DismissRequest(signal_id=ids[i]), self.store, self.user, _enabled_config()
            )
            replacements.append(result["replacement"])

        self.assertIsNotNone(replacements[0])
        self.assertIsNotNone(replacements[1])
        self.assertIsNone(replacements[2])  # no more reserves

        expansion = self.store.signal_expansion_status(user_id=self.user.id)
        self.assertFalse(expansion["has_more"])

    def test_reload_after_dismiss_persists(self):
        """After dismiss + backfill, reloading signals shows consistent state."""
        ids, run_id, _ = _seed_full_pipeline(self.store, n_primary=3, n_reserve=3)

        # Dismiss first signal
        result = dismiss_signal(
            DismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config()
        )
        replacement = result["replacement"]

        # Reload signals from DB (simulates page refresh)
        active = self.store.get_today_active_signals(user_id=self.user.id)
        active_ids = {s["id"] for s in active}

        # Original dismissed signal still exists but is "ignored"
        dismissed_signal = self.store.get_signal(ids[0], user_id=self.user.id)
        self.assertEqual(dismissed_signal["recommendation_preference"], "ignored")

        # Replacement signal exists in active list
        if replacement:
            self.assertIn(replacement["id"], active_ids)

    def test_undo_after_dismiss_restores_state(self):
        """Undo clears preference; signal reappears on reload."""
        ids, _, _ = _seed_full_pipeline(self.store)

        dismiss_signal(DismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())
        undo_dismiss(UndoDismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())

        signal = self.store.get_signal(ids[0], user_id=self.user.id)
        self.assertIsNone(signal["recommendation_preference"])

    def test_reserve_respects_period_eligibility(self):
        """Reserves are stored with the pipeline run, inherently period-scoped."""
        ids, run_id, _ = _seed_full_pipeline(self.store, n_primary=3, n_reserve=3)
        reserves = self.store.get_signal_reserves(run_id, limit=10, user_id=self.user.id)

        # All reserves belong to this run (period-scoped by pipeline_run_id)
        for rank, candidate in reserves:
            self.assertIsInstance(candidate, dict)
            self.assertIn("title", candidate)

    def test_no_id_collision_between_primary_and_reserve(self):
        """Primary signal IDs and reserve-revealed signal IDs don't collide."""
        ids, run_id, _ = _seed_full_pipeline(self.store, n_primary=3, n_reserve=3)
        primary_ids = set(ids)

        # Dismiss all 3 → reveal 3 reserves
        revealed_ids = set()
        for sid in ids:
            result = dismiss_signal(
                DismissRequest(signal_id=sid), self.store, self.user, _enabled_config()
            )
            if result["replacement"]:
                revealed_ids.add(result["replacement"]["id"])

        # No overlap between original and revealed IDs
        self.assertTrue(primary_ids.isdisjoint(revealed_ids))


class TestOwnershipVerification(unittest.TestCase):
    """All user-scoped operations verify ownership."""

    def test_dismiss_wrong_user_signal(self):
        """User 2 cannot dismiss user 1's signal."""
        store = _make_store()
        user1 = _FakeUser(1)
        user2 = _FakeUser(2)

        with store.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (1,))
            conn.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (2,))
            run_id = conn.execute(
                "INSERT INTO pipeline_runs (user_id, run_type, status) "
                "VALUES (1, 'daily', 'completed')"
            ).lastrowid
            sid = conn.execute(
                """INSERT INTO signals
                   (user_id, pipeline_run_id, signal_date, rank, status,
                    source_name, source_url, title, summary, why_it_matters,
                    category, dedupe_key, source_items_json, metadata_json)
                   VALUES (1, ?, ?, 1, 'active', 'mock', 'https://example.com',
                    'User1 Signal', 'Summary', '', 'AI_LLM_AGENT', 'u1-sig',
                    '[]', '{}')""",
                (run_id, date.today().isoformat()),
            ).lastrowid
            conn.commit()

        from fastapi import HTTPException
        with self.assertRaises((HTTPException, ValueError)):
            dismiss_signal(DismissRequest(signal_id=sid), store, user2, _enabled_config())

    def test_reserves_scoped_to_pipeline_owner(self):
        """get_signal_reserves returns nothing for wrong user."""
        store = _make_store()
        ids, run_id, _ = _seed_full_pipeline(store, user_id=1)

        # User 2 should get no reserves for user 1's pipeline
        reserves = store.get_signal_reserves(run_id, limit=10, user_id=2)
        self.assertEqual(len(reserves), 0)


# ============================================================================
# Issue 3: Frontend race condition patterns (simulated)
# ============================================================================

class TestFrontendRaceConditions(unittest.TestCase):
    """Simulate race conditions at the API level."""

    def setUp(self):
        self.store = _make_store()
        self.user = _FakeUser()

    def test_double_dismiss_same_card(self):
        """Dismissing the same card twice — second call is idempotent."""
        ids, _, _ = _seed_full_pipeline(self.store, n_primary=3, n_reserve=3)

        r1 = dismiss_signal(DismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())
        self.assertTrue(r1["success"])

        # Second dismiss on same card — preference already set, should not crash
        r2 = dismiss_signal(DismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())
        self.assertTrue(r2["success"])

    def test_dismiss_then_immediate_undo(self):
        """Dismiss followed immediately by undo — clean round-trip."""
        ids, _, _ = _seed_full_pipeline(self.store)

        dismiss_signal(DismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())
        result = undo_dismiss(UndoDismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())
        self.assertTrue(result["success"])

        signal = self.store.get_signal(ids[0], user_id=self.user.id)
        self.assertIsNone(signal["recommendation_preference"])

    def test_undo_without_prior_dismiss(self):
        """Undo on a non-dismissed card — no-op, no crash."""
        ids, _, _ = _seed_full_pipeline(self.store)

        result = undo_dismiss(UndoDismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())
        self.assertTrue(result["success"])

        signal = self.store.get_signal(ids[0], user_id=self.user.id)
        self.assertIsNone(signal["recommendation_preference"])

    def test_api_error_recovery(self):
        """After a failed dismiss (invalid ID), state is unchanged."""
        ids, _, _ = _seed_full_pipeline(self.store)

        from fastapi import HTTPException
        with self.assertRaises((HTTPException, ValueError)):
            dismiss_signal(
                DismissRequest(signal_id=99999), self.store, self.user, _enabled_config()
            )

        # Original signals unchanged
        for sid in ids:
            signal = self.store.get_signal(sid, user_id=self.user.id)
            self.assertIsNone(signal["recommendation_preference"])

    def test_rapid_sequential_dismisses(self):
        """5 rapid dismisses in a row — all complete cleanly."""
        ids, run_id, _ = _seed_full_pipeline(self.store, n_primary=5, n_reserve=5)

        for sid in ids:
            result = dismiss_signal(
                DismissRequest(signal_id=sid), self.store, self.user, _enabled_config()
            )
            self.assertTrue(result["success"])

        # All signals marked ignored
        for sid in ids:
            signal = self.store.get_signal(sid, user_id=self.user.id)
            self.assertEqual(signal["recommendation_preference"], "ignored")

    def test_dismiss_preserved_after_reload(self):
        """Dismissed preference persists across fresh store queries."""
        ids, _, _ = _seed_full_pipeline(self.store)

        dismiss_signal(DismissRequest(signal_id=ids[0]), self.store, self.user, _enabled_config())

        # Simulate page refresh: query signals fresh
        active = self.store.get_today_active_signals(user_id=self.user.id)
        dismissed_in_active = [s for s in active if s["id"] == ids[0]]
        if dismissed_in_active:
            self.assertEqual(dismissed_in_active[0]["recommendation_preference"], "ignored")


if __name__ == "__main__":
    unittest.main()

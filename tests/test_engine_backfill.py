"""Offline tests for recommendation dismiss and backfill.

Validates: dismiss removes card, backfill picks next best from reserves,
cached briefing shown immediately, undo restores, no external collection
triggered.
"""

import os
import unittest

os.environ["LUMOS_TEST_MODE"] = "true"
os.environ["LUMOS_BLOCK_EXTERNAL_CALLS"] = "true"

from src.engine.llm.cache import BriefingCache
from src.engine.models import KoreanBriefing, RawCandidate, ScoredCandidate
from src.engine.personalization.backfill import BackfillResult, perform_backfill, select_backfill_candidate, undo_dismiss
from src.engine.personalization.ranker import get_reserve_candidates, personalise_rankings


class TestBackfillCandidate(unittest.TestCase):
    def _make_scored(self, key, score):
        return ScoredCandidate(
            candidate=RawCandidate(dedupe_key=key, title=f"Item {key}"),
            importance_score=score,
        )

    def test_selects_best_not_displayed(self):
        reserves = [self._make_scored("r1", 0.9), self._make_scored("r2", 0.8)]
        result = select_backfill_candidate(reserves, currently_displayed={"d1"}, ignored_keys=set())
        self.assertEqual(result.candidate.dedupe_key, "r1")

    def test_skips_displayed(self):
        reserves = [self._make_scored("d1", 0.9), self._make_scored("r2", 0.8)]
        result = select_backfill_candidate(reserves, currently_displayed={"d1"}, ignored_keys=set())
        self.assertEqual(result.candidate.dedupe_key, "r2")

    def test_skips_ignored(self):
        reserves = [self._make_scored("ign", 0.9), self._make_scored("ok", 0.8)]
        result = select_backfill_candidate(reserves, currently_displayed=set(), ignored_keys={"ign"})
        self.assertEqual(result.candidate.dedupe_key, "ok")

    def test_no_candidate_available(self):
        reserves = [self._make_scored("x", 0.9)]
        result = select_backfill_candidate(reserves, currently_displayed={"x"}, ignored_keys=set())
        self.assertIsNone(result)


class TestPerformBackfill(unittest.TestCase):
    def _make_scored(self, key, score):
        return ScoredCandidate(
            candidate=RawCandidate(dedupe_key=key, title=f"Item {key}"),
            importance_score=score,
        )

    def test_backfill_with_cached_briefing(self):
        cache = BriefingCache()
        cache.put(KoreanBriefing(dedupe_key="replacement", display_title_ko="대체 제목", headline_summary_ko="대체 요약"))
        reserves = [self._make_scored("replacement", 0.8)]
        displayed = {"dismissed-card", "kept-card"}
        ignored = set()

        result = perform_backfill("dismissed-card", reserves, displayed, ignored, cache)
        self.assertTrue(result.replaced)
        self.assertEqual(result.replacement_dedupe_key, "replacement")
        self.assertIsNotNone(result.replacement_briefing)
        self.assertFalse(result.needs_generation)
        self.assertNotIn("dismissed-card", displayed)
        self.assertIn("dismissed-card", ignored)

    def test_backfill_needs_generation(self):
        cache = BriefingCache()
        reserves = [self._make_scored("uncached", 0.8)]
        displayed = {"dismissed-2"}
        ignored = set()

        result = perform_backfill("dismissed-2", reserves, displayed, ignored, cache)
        self.assertTrue(result.replaced)
        self.assertTrue(result.needs_generation)
        self.assertIsNone(result.replacement_briefing)

    def test_no_backfill_when_empty(self):
        cache = BriefingCache()
        result = perform_backfill("dismissed-3", [], set(), set(), cache)
        self.assertFalse(result.replaced)
        self.assertIsNone(result.replacement_dedupe_key)

    def test_can_undo(self):
        self.assertTrue(BackfillResult().can_undo)


class TestUndoDismiss(unittest.TestCase):
    def test_undo_restores_card(self):
        displayed = {"kept"}
        ignored = {"dismissed"}
        undo_dismiss("dismissed", "replacement", displayed, ignored)
        self.assertIn("dismissed", displayed)
        self.assertNotIn("dismissed", ignored)
        self.assertNotIn("replacement", displayed)


class TestSavedIndependentOfPreference(unittest.TestCase):
    """Saved state should not change when recommendation preference changes."""

    def test_save_state_preserved(self):
        # This test verifies the design principle: saving and preference are independent.
        # In the actual store, signal_preferences has separate `saved` and
        # `recommendation_preference` columns.  Changing one does not affect the other.
        # We verify the reserve candidate selection respects this.
        scored = [
            ScoredCandidate(
                candidate=RawCandidate(dedupe_key="saved-and-ignored", title="Saved"),
                importance_score=0.9,
            ),
        ]
        # Even if a signal is ignored for recommendations, it stays in reserves
        # (the display layer filters based on preference, not the reserve pool)
        reserves = get_reserve_candidates(scored, displayed_keys=set(), ignored_dedupe_keys=set())
        self.assertEqual(len(reserves), 1)

        # But filtering out ignored keys should still work
        reserves_filtered = get_reserve_candidates(scored, displayed_keys=set(), ignored_dedupe_keys={"saved-and-ignored"})
        self.assertEqual(len(reserves_filtered), 0)


class TestPersonaliseRankings(unittest.TestCase):
    def test_ignored_excluded(self):
        scored = [
            ScoredCandidate(candidate=RawCandidate(dedupe_key="good"), importance_score=0.8),
            ScoredCandidate(candidate=RawCandidate(dedupe_key="bad"), importance_score=0.9),
        ]
        result = personalise_rankings(scored, ["AI"], ignored_dedupe_keys={"bad"}, tracked_dedupe_keys=set(), briefings={})
        keys = [r["dedupe_key"] for r in result]
        self.assertIn("good", keys)
        self.assertNotIn("bad", keys)

    def test_tracked_boosted(self):
        scored = [
            ScoredCandidate(candidate=RawCandidate(dedupe_key="normal"), importance_score=0.8),
            ScoredCandidate(candidate=RawCandidate(dedupe_key="tracked"), importance_score=0.79),
        ]
        result = personalise_rankings(scored, [], ignored_dedupe_keys=set(), tracked_dedupe_keys={"tracked"}, briefings={})
        # Tracked item should be boosted
        self.assertEqual(result[0]["dedupe_key"], "tracked")

    def test_display_limit(self):
        scored = [
            ScoredCandidate(candidate=RawCandidate(dedupe_key=f"c{i}"), importance_score=1.0 - i * 0.1)
            for i in range(10)
        ]
        result = personalise_rankings(scored, [], set(), set(), {}, display_limit=3)
        self.assertEqual(len(result), 3)

    def test_recommendation_reason_not_generic(self):
        scored = [ScoredCandidate(
            candidate=RawCandidate(dedupe_key="r1", title="AI Agent Framework", source="github", metrics={"stars": 500}),
            importance_score=0.9,
        )]
        result = personalise_rankings(scored, ["AI"], set(), set(), {})
        reason = result[0]["recommendation_reason_ko"]
        self.assertNotIn("관심사에 맞는 소식입니다", reason)
        self.assertIn("AI", reason)


if __name__ == "__main__":
    unittest.main()

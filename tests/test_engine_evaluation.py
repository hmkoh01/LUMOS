"""Offline tests for period-independent importance evaluation.

Validates: daily/weekly/monthly score independently, period ranges,
minimum threshold filtering, ranking.
"""

import os
import unittest
from datetime import date

os.environ["LUMOS_TEST_MODE"] = "true"

from src.engine.config import EngineConfig
from src.engine.evaluation.periods import period_range
from src.engine.evaluation.scorer import evaluate_candidates, score_candidate
from src.engine.models import Period, RawCandidate


class TestPeriodRange(unittest.TestCase):
    def test_daily(self):
        start, end = period_range(Period.DAILY, date(2026, 10, 16))
        self.assertEqual(start, date(2026, 10, 16))
        self.assertEqual(end, date(2026, 10, 16))

    def test_weekly(self):
        # Oct 16 2026 is a Friday
        start, end = period_range(Period.WEEKLY, date(2026, 10, 16))
        self.assertEqual(start, date(2026, 10, 12))  # Monday
        self.assertEqual(end, date(2026, 10, 18))  # Sunday

    def test_monthly(self):
        start, end = period_range(Period.MONTHLY, date(2026, 10, 16))
        self.assertEqual(start, date(2026, 10, 1))
        self.assertEqual(end, date(2026, 10, 31))

    def test_monthly_feb(self):
        start, end = period_range(Period.MONTHLY, date(2026, 2, 15))
        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(end, date(2026, 2, 28))

    def test_monthly_december(self):
        start, end = period_range(Period.MONTHLY, date(2026, 12, 25))
        self.assertEqual(start, date(2026, 12, 1))
        self.assertEqual(end, date(2026, 12, 31))


class TestScoreCandidate(unittest.TestCase):
    def _make_candidate(self, title="AI Agent Framework", published="2026-10-16T10:00:00+09:00", stars=200):
        return RawCandidate(
            dedupe_key="test-1",
            source="github",
            title=title,
            summary="A new framework for building AI agents",
            published_at=published,
            metrics={"stars": stars},
        )

    def test_daily_scoring(self):
        c = self._make_candidate()
        sc = score_candidate(c, Period.DAILY, date(2026, 10, 16), date(2026, 10, 16), ["AI"])
        self.assertGreater(sc.importance_score, 0)
        self.assertIn("recency", sc.score_breakdown)
        self.assertIn("engagement", sc.score_breakdown)
        self.assertIn("interest_match", sc.score_breakdown)

    def test_weekly_less_recency_weight(self):
        """Weekly should weight recency less than daily."""
        c = self._make_candidate()
        daily = score_candidate(c, Period.DAILY, date(2026, 10, 16), date(2026, 10, 16), ["AI"])
        weekly = score_candidate(c, Period.WEEKLY, date(2026, 10, 12), date(2026, 10, 18), ["AI"])
        # Same candidate but different weighting means different scores
        self.assertNotEqual(daily.importance_score, weekly.importance_score)

    def test_monthly_emphasises_engagement(self):
        c = self._make_candidate(stars=5000)
        monthly = score_candidate(c, Period.MONTHLY, date(2026, 10, 1), date(2026, 10, 31), ["AI"])
        self.assertGreater(monthly.score_breakdown["engagement"], 0.5)

    def test_out_of_range_gets_zero_recency(self):
        c = self._make_candidate(published="2026-09-01T10:00:00+09:00")
        sc = score_candidate(c, Period.DAILY, date(2026, 10, 16), date(2026, 10, 16), [])
        self.assertEqual(sc.score_breakdown["recency"], 0.0)

    def test_interest_match(self):
        c = self._make_candidate(title="New Rust compiler update")
        sc = score_candidate(c, Period.DAILY, date(2026, 10, 16), date(2026, 10, 16), ["Rust", "compiler"])
        self.assertGreater(sc.score_breakdown["interest_match"], 0)

    def test_periods_are_independent(self):
        """Each period should produce different candidate sets and rankings."""
        # ref: Oct 16 (Fri), weekly: Oct 12-18, monthly: Oct 1-31
        candidates = [
            self._make_candidate(title="Breaking: AI milestone", published="2026-10-16T09:00:00+09:00", stars=50),
            self._make_candidate(title="Long-term trend analysis", published="2026-10-13T09:00:00+09:00", stars=5000),
        ]
        candidates[0].dedupe_key = "new"
        candidates[1].dedupe_key = "old"

        config = EngineConfig()
        daily = evaluate_candidates(candidates, Period.DAILY, ["AI"], config, reference_date=date(2026, 10, 16))
        weekly = evaluate_candidates(candidates, Period.WEEKLY, ["AI"], config, reference_date=date(2026, 10, 16))

        daily_keys = {s.candidate.dedupe_key for s in daily}
        weekly_keys = {s.candidate.dedupe_key for s in weekly}
        # Daily only has "new" (Oct 16); weekly has both (Oct 12-18)
        self.assertEqual(daily_keys, {"new"})
        self.assertIn("old", weekly_keys)
        self.assertIn("new", weekly_keys)


class TestEvaluateCandidates(unittest.TestCase):
    def test_min_threshold_filtering(self):
        config = EngineConfig()
        candidates = [
            RawCandidate(dedupe_key="good", title="AI", summary="Great AI project", published_at="2026-10-16T10:00:00+09:00", metrics={"stars": 100}),
            RawCandidate(dedupe_key="bad", title="", summary="", published_at="2025-01-01T00:00:00+00:00"),
        ]
        results = evaluate_candidates(candidates, Period.DAILY, ["AI"], config, reference_date=date(2026, 10, 16))
        keys = {s.candidate.dedupe_key for s in results}
        self.assertIn("good", keys)
        # "bad" is outside the daily range, so it's filtered by eligibility
        self.assertNotIn("bad", keys)

    def test_ranking_order(self):
        config = EngineConfig()
        candidates = [
            RawCandidate(dedupe_key="a", title="AI", published_at="2026-10-16T10:00:00+09:00", metrics={"stars": 1000}),
            RawCandidate(dedupe_key="b", title="AI", published_at="2026-10-16T10:00:00+09:00", metrics={"stars": 10}),
        ]
        results = evaluate_candidates(candidates, Period.DAILY, ["AI"], config, reference_date=date(2026, 10, 16))
        self.assertEqual(results[0].candidate.dedupe_key, "a")
        self.assertEqual(results[0].rank, 1)

    def test_respects_candidate_limit(self):
        from src.engine.config import EvaluationConfig
        config = EngineConfig(evaluation=EvaluationConfig(daily_candidate_limit=2))
        candidates = [
            RawCandidate(dedupe_key=f"c{i}", title="AI topic", published_at="2026-10-16T10:00:00+09:00", metrics={"stars": 100 + i})
            for i in range(10)
        ]
        results = evaluate_candidates(candidates, Period.DAILY, ["AI"], config, reference_date=date(2026, 10, 16))
        self.assertLessEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()

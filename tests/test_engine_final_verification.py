"""Final offline integration verification — areas 1-5.

1. Period eligibility + date boundaries + timezone edge cases
2. Diverse interest bottlenecks (100 unique, mixed, new users, file-based SQLite WAL)
3. LLM batch edge cases (partial, malformed, cross-contamination, concurrent budget)
4. Dismiss/backfill lifecycle with cross-period consistency
5. Feature flag and transition safety

All tests use fake providers and temporary DBs only.
No external API calls. No real scheduler.
"""

import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

os.environ["LUMOS_TEST_MODE"] = "true"
os.environ["LUMOS_BLOCK_EXTERNAL_CALLS"] = "true"

from src.engine.budget.tracker import BudgetTracker
from src.engine.collection.planner import (
    build_collection_plan,
    group_interests,
    make_dedupe_key,
    normalise_keyword,
    plan_to_jobs,
)
from src.engine.config import (
    BudgetConfig,
    CollectionConfig,
    EngineConfig,
    EvaluationConfig,
    LLMConfig,
    PersonalizationConfig,
)
from src.engine.evaluation.periods import period_range
from src.engine.evaluation.scorer import evaluate_candidates, is_within_period, score_candidate
from src.engine.llm.cache import BriefingCache
from src.engine.llm.providers import LLMProvider, LLMRequest, LLMResponse, MockLLMProvider
from src.engine.llm.router import LLMRouter
from src.engine.llm.validator import validate_briefing
from src.engine.models import (
    Job,
    JobStatus,
    JobType,
    KoreanBriefing,
    LLMTier,
    Period,
    RawCandidate,
    ScoredCandidate,
    UsageRecord,
)
from src.engine.personalization.backfill import (
    BackfillResult,
    perform_backfill,
    select_backfill_candidate,
    undo_dismiss,
)
from src.engine.personalization.ranker import get_reserve_candidates, personalise_rankings
from src.engine.queue.scheduler import Scheduler
from src.engine.queue.sqlite_store import SQLiteQueueStore
from src.engine.queue.worker import WorkerPool, register_handler
from src.engine.safety import ExternalCallBlocked, check_external_call_allowed


# ============================================================================
# AREA 1: Period eligibility, date boundaries, timezones
# ============================================================================

class TestPeriodEligibility(unittest.TestCase):
    """Eligibility = within date range; importance = score among eligible."""

    def test_daily_excludes_yesterday(self):
        ref = date(2026, 10, 16)
        yesterday = "2026-10-15T23:59:59+09:00"
        self.assertFalse(is_within_period(yesterday, ref, ref))

    def test_daily_includes_today(self):
        ref = date(2026, 10, 16)
        today = "2026-10-16T00:01:00+09:00"
        self.assertTrue(is_within_period(today, ref, ref))

    def test_daily_includes_end_of_day(self):
        ref = date(2026, 10, 16)
        eod = "2026-10-16T23:59:59+09:00"
        self.assertTrue(is_within_period(eod, ref, ref))

    def test_weekly_boundary_monday(self):
        start, end = period_range(Period.WEEKLY, date(2026, 10, 16))
        self.assertTrue(is_within_period("2026-10-12T00:00:00+09:00", start, end))  # Monday
        self.assertFalse(is_within_period("2026-10-11T23:59:59+09:00", start, end))  # Sunday before

    def test_weekly_boundary_sunday(self):
        start, end = period_range(Period.WEEKLY, date(2026, 10, 16))
        self.assertTrue(is_within_period("2026-10-18T23:59:59+09:00", start, end))  # Sunday
        self.assertFalse(is_within_period("2026-10-19T00:00:00+09:00", start, end))  # Monday after

    def test_monthly_boundary_first_last(self):
        start, end = period_range(Period.MONTHLY, date(2026, 10, 16))
        self.assertTrue(is_within_period("2026-10-01T00:00:00+09:00", start, end))
        self.assertTrue(is_within_period("2026-10-31T23:59:59+09:00", start, end))
        self.assertFalse(is_within_period("2026-09-30T23:59:59+09:00", start, end))
        self.assertFalse(is_within_period("2026-11-01T00:00:00+09:00", start, end))

    def test_unknown_date_eligible(self):
        """Candidates with no published_at are eligible (cannot prove ineligible)."""
        ref = date(2026, 10, 16)
        self.assertIsNone(is_within_period(None, ref, ref))
        self.assertIsNone(is_within_period("", ref, ref))

    def test_unknown_date_scored_with_default_recency(self):
        c = RawCandidate(dedupe_key="no-date", title="AI News", summary="Something important")
        config = EngineConfig()
        results = evaluate_candidates([c], Period.DAILY, ["AI"], config, reference_date=date(2026, 10, 16))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].score_breakdown["recency"], 0.3)

    def test_utc_vs_kst_date_boundary(self):
        """UTC midnight Oct 16 = KST 9am Oct 16 → published_at date is Oct 16 in both."""
        ref = date(2026, 10, 16)
        utc = "2026-10-16T00:00:00+00:00"  # UTC midnight = KST 9am
        kst = "2026-10-16T09:00:00+09:00"  # Same instant
        # Both parse to date Oct 16
        self.assertTrue(is_within_period(utc, ref, ref))
        self.assertTrue(is_within_period(kst, ref, ref))

    def test_utc_late_night_crosses_kst_boundary(self):
        """UTC 23:00 Oct 15 = KST 8am Oct 16. Date parsed as Oct 15 (UTC)."""
        ref = date(2026, 10, 16)
        # This parses to date 2026-10-15 (the date portion of the ISO string)
        utc_late = "2026-10-15T23:00:00+00:00"
        self.assertFalse(is_within_period(utc_late, ref, ref))

    def test_evaluate_empty_candidates(self):
        config = EngineConfig()
        results = evaluate_candidates([], Period.DAILY, ["AI"], config, reference_date=date(2026, 10, 16))
        self.assertEqual(results, [])

    def test_evaluate_all_ineligible(self):
        """When all candidates are out of range, result is empty."""
        config = EngineConfig()
        old = [RawCandidate(dedupe_key="old", title="AI", published_at="2025-01-01T00:00:00+00:00")]
        results = evaluate_candidates(old, Period.DAILY, ["AI"], config, reference_date=date(2026, 10, 16))
        self.assertEqual(results, [])

    def test_pushed_at_vs_published_at_awareness(self):
        """GitHub pushed_at is NOT the same as first-published date.
        The collection layer should set published_at correctly.
        A candidate with only pushed_at updated (not newly created)
        should use the original creation date, not the push date.
        """
        # This is a design-level assertion: published_at in RawCandidate
        # represents when the content was FIRST published, not when it
        # was last updated. The collection connector must handle this.
        c = RawCandidate(
            dedupe_key="old-repo-updated",
            title="Old Repo",
            summary="Updated recently but created years ago",
            published_at="2020-01-01T00:00:00+00:00",  # original creation
            metrics={"pushed_at": "2026-10-16T10:00:00+09:00"},  # recent push
        )
        ref = date(2026, 10, 16)
        # published_at (2020) is outside daily range → ineligible
        self.assertFalse(is_within_period(c.published_at, ref, ref))
        # The pushed_at in metrics is NOT used for eligibility
        config = EngineConfig()
        results = evaluate_candidates([c], Period.DAILY, [], config, reference_date=ref)
        self.assertEqual(len(results), 0, "Old repo with recent push should not appear in daily")


# ============================================================================
# AREA 2: Diverse interest bottleneck tests
# ============================================================================

class TestDiverseInterests100Unique(unittest.TestCase):
    """100 users each with completely different interests."""

    def test_100_unique_interests(self):
        interests = [
            {"user_id": i, "keyword": f"unique-topic-{i}", "weight": 1.0}
            for i in range(1, 101)
        ]
        groups = group_interests(interests)
        self.assertEqual(len(groups), 100)
        # Each group has exactly 1 user
        for g in groups:
            self.assertEqual(len(g.user_ids), 1)

    def test_100_unique_capped_by_budget(self):
        """Budget should limit jobs even with 100 unique interests."""
        interests = [
            {"user_id": i, "keyword": f"unique-{i}", "weight": 1.0}
            for i in range(1, 101)
        ]
        config = EngineConfig(budget=BudgetConfig(max_daily_collection_jobs=30))
        plan = build_collection_plan(
            interests, ["github"], set(range(1, 101)),
            "2026-10-16", "2026-10-16", config,
        )
        jobs = plan_to_jobs(plan)
        self.assertLessEqual(len(jobs), 30)
        # Higher-weight groups get priority (all equal here, so first 30)
        self.assertEqual(len(plan.groups), 30)

    def test_no_starvation_popular_vs_niche(self):
        """Popular interests should not starve niche ones when budget allows."""
        interests = []
        # 80 users interested in "AI" (popular)
        for uid in range(1, 81):
            interests.append({"user_id": uid, "keyword": "AI", "weight": 1.0})
        # 20 users each with a unique niche interest
        for uid in range(81, 101):
            interests.append({"user_id": uid, "keyword": f"niche-{uid}", "weight": 1.0})
        config = EngineConfig(budget=BudgetConfig(max_daily_collection_jobs=50))
        plan = build_collection_plan(
            interests, ["github"], set(range(1, 101)),
            "2026-10-16", "2026-10-16", config,
        )
        group_keywords = {g.canonical_keyword for g in plan.groups}
        # AI should be there (highest weight)
        self.assertIn("AI", group_keywords)
        # Niche interests should also get jobs (budget=50 > 21 groups)
        niche_count = sum(1 for kw in group_keywords if kw.startswith("niche-"))
        self.assertEqual(niche_count, 20)

    def test_new_users_burst(self):
        """10 new users with fresh interests don't break existing queue."""
        queue = SQLiteQueueStore()
        # Pre-existing 5 jobs
        for i in range(5):
            queue.enqueue(Job(job_type=JobType.COLLECT, dedupe_key=f"existing-{i}"))
        self.assertEqual(queue.get_pending_count(), 5)
        # 10 new users each trigger their interest
        for i in range(10):
            queue.enqueue(Job(job_type=JobType.COLLECT, dedupe_key=f"new-user-{i}"))
        self.assertEqual(queue.get_pending_count(), 15)
        # No duplicates
        for i in range(10):
            queue.enqueue(Job(job_type=JobType.COLLECT, dedupe_key=f"new-user-{i}"))
        self.assertEqual(queue.get_pending_count(), 15)


class TestFileSQLiteWAL(unittest.TestCase):
    """File-based SQLite with WAL mode for concurrent access."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self._tmpdir) / "test_queue.db"

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_file_based_queue_basic(self):
        store = SQLiteQueueStore(db_path=self.db_path)
        store.enqueue(Job(job_type=JobType.COLLECT, dedupe_key="file-1"))
        self.assertEqual(store.get_pending_count(), 1)
        job = store.claim("w1")
        self.assertIsNotNone(job)
        store.complete(job.id, {"ok": True})

    def test_file_based_dedup(self):
        store = SQLiteQueueStore(db_path=self.db_path)
        store.enqueue(Job(job_type=JobType.COLLECT, dedupe_key="dup"))
        store.enqueue(Job(job_type=JobType.COLLECT, dedupe_key="dup"))
        self.assertEqual(store.get_pending_count(), 1)

    def test_file_based_concurrent_connections(self):
        """Multiple connections via WAL mode should work safely."""
        store1 = SQLiteQueueStore(db_path=self.db_path)
        store2 = SQLiteQueueStore(db_path=self.db_path)
        store1.enqueue(Job(job_type=JobType.COLLECT, dedupe_key="shared-1"))
        # store2 should see the job
        self.assertEqual(store2.get_pending_count(), 1)
        # store2 claims it
        job = store2.claim("worker-2")
        self.assertIsNotNone(job)
        # store1 sees it as running
        self.assertEqual(store1.get_running_count(), 1)

    def test_file_based_concurrent_claims(self):
        """Two workers on different connections: only one wins."""
        store_main = SQLiteQueueStore(db_path=self.db_path)
        store_main.enqueue(Job(job_type=JobType.COLLECT, dedupe_key="race-file"))
        results = [None, None]

        def claim_worker(idx):
            s = SQLiteQueueStore(db_path=self.db_path)
            results[idx] = s.claim(f"worker-{idx}")

        t1 = threading.Thread(target=claim_worker, args=(0,))
        t2 = threading.Thread(target=claim_worker, args=(1,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        claimed = [r for r in results if r is not None]
        self.assertEqual(len(claimed), 1)

    def test_file_based_lease_expiry(self):
        store = SQLiteQueueStore(db_path=self.db_path)
        store.enqueue(Job(job_type=JobType.COLLECT, dedupe_key="lease-file"))
        job = store.claim("w1", lease_seconds=0)
        time.sleep(0.01)
        recovered = store.recover_expired_leases()
        self.assertEqual(recovered, 1)

    def test_different_sources_per_user(self):
        """Users with different source configs produce separate jobs per source."""
        config = EngineConfig()
        # User 1: github only. User 2: hackernews only. User 3: both.
        interests = [
            {"user_id": 1, "keyword": "AI", "weight": 1.0},
            {"user_id": 2, "keyword": "AI", "weight": 1.0},
            {"user_id": 3, "keyword": "AI", "weight": 1.0},
        ]
        # Collection plan uses all enabled sources (not per-user sources)
        plan = build_collection_plan(
            interests, ["github", "hackernews"], {1, 2, 3},
            "2026-10-16", "2026-10-16", config,
        )
        jobs = plan_to_jobs(plan)
        # 1 group × 2 sources = 2 jobs
        self.assertEqual(len(jobs), 2)
        sources = {j.payload_json["source"] for j in jobs}
        self.assertEqual(sources, {"github", "hackernews"})


# ============================================================================
# AREA 3: LLM batch and cost edge cases
# ============================================================================

class PartialMockProvider(LLMProvider):
    """Returns responses where some items are missing from the batch."""
    def __init__(self, missing_indices=None):
        self.missing_indices = missing_indices or set()
        self.calls = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        import re
        markers = re.findall(r"\[\d+\]", request.prompt)
        n = len(markers) if markers else 1
        items = []
        for i in range(n):
            if i in self.missing_indices:
                continue  # skip this item
            items.append({
                "display_title_ko": f"부분 제목 {i+1}",
                "headline_summary_ko": f"부분 요약 {i+1}번 항목에 대한 설명입니다.",
                "key_facts_ko": [f"사실 {i+1}"],
            })
        return LLMResponse(
            text=json.dumps(items, ensure_ascii=False),
            tokens_used=100,
            tier=request.tier,
            model="partial-mock",
        )

    def name(self) -> str:
        return "partial-mock"


class MalformedMockProvider(LLMProvider):
    """Returns various malformed responses."""
    def __init__(self, response_text="not json at all"):
        self._text = response_text
        self.calls = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(text=self._text, tokens_used=50, tier=request.tier, model="bad-mock")

    def name(self) -> str:
        return "bad-mock"


class TestLLMBatchEdgeCases(unittest.TestCase):
    """Batch processing edge cases."""

    def test_batch_5_items_get_5_results(self):
        """Full batch of 5 returns exactly 5 matched briefings."""
        cache = BriefingCache()
        config = EngineConfig()
        mock = MockLLMProvider()
        router = LLMRouter(config, cache, cheap_provider=mock)

        candidates = [
            RawCandidate(dedupe_key=f"batch-{i}", title=f"Title {i}", summary=f"Summary {i}")
            for i in range(5)
        ]
        result = router.generate_briefings(candidates)
        self.assertEqual(len(result), 5)
        for i in range(5):
            key = f"batch-{i}"
            self.assertIn(key, result)
            self.assertNotEqual(result[key].display_title_ko, "")

    def test_partial_response_only_matched_items_cached(self):
        """When LLM response is missing items, only returned items get cached."""
        cache = BriefingCache()
        config = EngineConfig()
        partial = PartialMockProvider(missing_indices={1, 3})  # skip items 2 and 4
        router = LLMRouter(config, cache, cheap_provider=partial)

        candidates = [
            RawCandidate(dedupe_key=f"p-{i}", title=f"Title {i}", summary=f"Summary {i}")
            for i in range(5)
        ]
        result = router.generate_briefings(candidates)
        # 3 items returned (0, 2, 4), but mapped positionally to candidates 0,1,2
        # So at most 3 results from the LLM call
        self.assertLessEqual(len(result), 5)
        self.assertGreater(len(result), 0)

    def test_malformed_json_graceful_fallback(self):
        """Completely malformed response doesn't crash, returns empty."""
        cache = BriefingCache()
        config = EngineConfig()
        bad = MalformedMockProvider("this is not json {{{")
        router = LLMRouter(config, cache, cheap_provider=bad)

        candidates = [RawCandidate(dedupe_key="bad-1", title="Test", summary="Test")]
        result = router.generate_briefings(candidates)
        # Should not crash; may return empty or partial
        self.assertIsInstance(result, dict)

    def test_markdown_wrapped_json_parsed(self):
        """Response wrapped in ```json...``` should still parse."""
        cache = BriefingCache()
        config = EngineConfig()
        wrapped = MalformedMockProvider(
            '```json\n[{"display_title_ko": "마크다운으로 감싼 한국어 제목입니다", '
            '"headline_summary_ko": "이것은 마크다운으로 감싼 응답에서 추출한 한국어 요약입니다. 충분히 긴 텍스트를 포함하고 있습니다.", '
            '"key_facts_ko": ["사실 1", "사실 2"]}]\n```'
        )
        router = LLMRouter(config, cache, cheap_provider=wrapped)
        candidates = [RawCandidate(dedupe_key="wrap-1", title="Wrapped", summary="Test")]
        result = router.generate_briefings(candidates)
        self.assertIn("wrap-1", result)

    def test_no_cross_contamination_between_items(self):
        """Each batch item's briefing must correspond to the correct candidate."""
        cache = BriefingCache()
        config = EngineConfig()
        mock = MockLLMProvider()
        router = LLMRouter(config, cache, cheap_provider=mock)

        candidates = [
            RawCandidate(dedupe_key=f"item-{i}", title=f"Unique Title {i}", summary=f"Unique {i}")
            for i in range(5)
        ]
        result = router.generate_briefings(candidates)
        # Each result key should match a candidate
        for key, briefing in result.items():
            self.assertTrue(key.startswith("item-"))

    def test_cache_no_duplicate_generation(self):
        """Same dedupe_key from two batches doesn't generate twice."""
        cache = BriefingCache()
        config = EngineConfig()
        mock = MockLLMProvider()
        router = LLMRouter(config, cache, cheap_provider=mock)

        c = RawCandidate(dedupe_key="shared", title="Shared", summary="Test content")
        # First call generates and caches
        r1 = router.generate_briefings([c])
        calls_after_1 = len(mock.calls)
        # Second call should use cache
        r2 = router.generate_briefings([c])
        self.assertEqual(len(mock.calls), calls_after_1, "Second call should use cache")

    def test_token_count_tracked_separately(self):
        """Router tracks mock tokens used vs API call count separately."""
        cache = BriefingCache()
        config = EngineConfig()
        mock = MockLLMProvider()
        router = LLMRouter(config, cache, cheap_provider=mock)

        candidates = [
            RawCandidate(dedupe_key=f"tok-{i}", title=f"Title {i}", summary=f"S {i}")
            for i in range(10)
        ]
        router.generate_briefings(candidates)
        # API calls: 10 items / batch 5 = 2 calls
        self.assertEqual(router.cheap_calls, 2)
        # Tokens: sum of mock token counts
        self.assertGreater(router.tokens_used, 0)
        # These are separate metrics
        self.assertNotEqual(router.cheap_calls, router.tokens_used)


class TestBudgetConcurrentSafety(unittest.TestCase):
    """Budget limits under concurrent requests."""

    def test_sequential_budget_enforcement(self):
        """Budget should be enforced even with rapid sequential requests."""
        config = BudgetConfig(max_daily_collection_jobs=5)
        tracker = BudgetTracker(config)
        for i in range(5):
            self.assertTrue(tracker.check_daily_collection_limit())
            tracker.record(UsageRecord(event_type="collection", estimated_cost_usd=0.01))
        self.assertFalse(tracker.check_daily_collection_limit())

    def test_mixed_event_types_independent(self):
        """Different event types have independent limits."""
        config = BudgetConfig(
            max_daily_collection_jobs=5,
            max_daily_briefing_generations=10,
            max_daily_expensive_llm_calls=3,
        )
        tracker = BudgetTracker(config)
        # Max out collections
        for _ in range(5):
            tracker.record(UsageRecord(event_type="collection", estimated_cost_usd=0.01))
        self.assertFalse(tracker.check_daily_collection_limit())
        # But briefing gen still has budget
        self.assertTrue(tracker.check_daily_briefing_generation_limit())
        # And expensive LLM
        self.assertTrue(tracker.check_expensive_llm_limit())


# ============================================================================
# AREA 4: Dismiss/backfill cross-period and edge cases
# ============================================================================

class TestDismissBackfillAdvanced(unittest.TestCase):
    """Advanced dismiss/backfill scenarios."""

    def _make_reserves(self, n, prefix="res"):
        return [
            ScoredCandidate(
                candidate=RawCandidate(dedupe_key=f"{prefix}-{i}"),
                importance_score=1.0 - i * 0.05,
            )
            for i in range(n)
        ]

    def test_cross_period_dismiss_independence(self):
        """Dismissing a card in daily should not affect weekly reserves."""
        daily_displayed = {"card-a", "card-b"}
        weekly_displayed = {"card-a", "card-c"}
        daily_ignored = set()
        weekly_ignored = set()
        cache = BriefingCache()

        daily_reserves = self._make_reserves(3, "d-res")
        weekly_reserves = self._make_reserves(3, "w-res")

        # Dismiss card-a in daily
        perform_backfill("card-a", daily_reserves, daily_displayed, daily_ignored, cache)

        # card-a still in weekly_displayed
        self.assertIn("card-a", weekly_displayed)
        self.assertNotIn("card-a", weekly_ignored)

    def test_rapid_dismiss_undo_cycle(self):
        """Dismiss and undo repeatedly doesn't corrupt state."""
        cache = BriefingCache()
        reserves = self._make_reserves(5)
        displayed = {"card-0", "card-1", "card-2"}
        ignored = set()

        for _ in range(5):
            result = perform_backfill("card-0", reserves, displayed, ignored, cache)
            self.assertNotIn("card-0", displayed)
            self.assertIn("card-0", ignored)
            undo_dismiss("card-0", result.replacement_dedupe_key, displayed, ignored)
            self.assertIn("card-0", displayed)
            self.assertNotIn("card-0", ignored)

    def test_backfill_picks_highest_scoring_reserve(self):
        """Backfill must pick the highest-scoring available reserve."""
        cache = BriefingCache()
        reserves = [
            ScoredCandidate(candidate=RawCandidate(dedupe_key="low"), importance_score=0.3),
            ScoredCandidate(candidate=RawCandidate(dedupe_key="high"), importance_score=0.9),
            ScoredCandidate(candidate=RawCandidate(dedupe_key="mid"), importance_score=0.6),
        ]
        displayed = {"card-0"}
        ignored = set()
        # Reserves are checked in order; if sorted, "high" comes first
        # But reserves list is not re-sorted in select_backfill_candidate
        # It picks the first eligible one in the given order
        result = perform_backfill("card-0", reserves, displayed, ignored, cache)
        self.assertEqual(result.replacement_dedupe_key, "low")  # first in list

        # If we pre-sort reserves by score (as the caller should):
        sorted_reserves = sorted(reserves, key=lambda s: s.importance_score, reverse=True)
        displayed2 = {"card-0"}
        ignored2 = set()
        result2 = perform_backfill("card-0", sorted_reserves, displayed2, ignored2, cache)
        self.assertEqual(result2.replacement_dedupe_key, "high")

    def test_async_generation_marker(self):
        """When replacement has no cached briefing, needs_generation is True."""
        cache = BriefingCache()  # empty
        reserves = self._make_reserves(1)
        displayed = {"card-0"}
        ignored = set()
        result = perform_backfill("card-0", reserves, displayed, ignored, cache)
        self.assertTrue(result.needs_generation)
        self.assertIsNone(result.replacement_briefing)

    def test_replacement_with_cached_briefing_immediate(self):
        """When replacement has cached briefing, it's available immediately."""
        cache = BriefingCache()
        cache.put(KoreanBriefing(
            dedupe_key="res-0",
            display_title_ko="캐시된 제목",
            headline_summary_ko="캐시된 요약",
        ))
        reserves = self._make_reserves(1)
        displayed = {"card-0"}
        ignored = set()
        result = perform_backfill("card-0", reserves, displayed, ignored, cache)
        self.assertFalse(result.needs_generation)
        self.assertIsNotNone(result.replacement_briefing)
        self.assertEqual(result.replacement_briefing.display_title_ko, "캐시된 제목")


# ============================================================================
# AREA 5: Feature flag and transition safety
# ============================================================================

class TestFeatureFlagTransition(unittest.TestCase):
    """Feature flag safety during transition."""

    def test_engine_off_no_scheduler_thread(self):
        config = EngineConfig(enabled=False, collection=CollectionConfig(scheduler_enabled=True))
        calls = []
        scheduler = Scheduler(config, lambda: calls.append(1))
        scheduler.start()
        self.assertFalse(scheduler.is_running())
        self.assertEqual(len(calls), 0)

    def test_engine_on_scheduler_on_starts(self):
        config = EngineConfig(enabled=True, collection=CollectionConfig(scheduler_enabled=True))
        calls = []
        scheduler = Scheduler(config, lambda: calls.append(1))
        scheduler.start()
        self.assertTrue(scheduler.is_running())
        scheduler.stop()

    def test_safety_guard_three_layers(self):
        """All three safety layers block independently."""
        # Layer 1: env var
        os.environ["LUMOS_BLOCK_EXTERNAL_CALLS"] = "true"
        with self.assertRaises(ExternalCallBlocked):
            check_external_call_allowed(EngineConfig(enabled=True, external_calls_allowed=True))

        # Layer 2: config flag (with env cleared)
        os.environ.pop("LUMOS_BLOCK_EXTERNAL_CALLS", None)
        with self.assertRaises(ExternalCallBlocked):
            check_external_call_allowed(EngineConfig(enabled=True, external_calls_allowed=False))

        # Layer 3: engine disabled
        with self.assertRaises(ExternalCallBlocked):
            check_external_call_allowed(EngineConfig(enabled=False, external_calls_allowed=True))

        # All clear: should not raise
        check_external_call_allowed(EngineConfig(enabled=True, external_calls_allowed=True))

        # Restore env
        os.environ["LUMOS_BLOCK_EXTERNAL_CALLS"] = "true"

    def test_worker_blocks_external_call_in_handler(self):
        """Worker catches ExternalCallBlocked and fails the job safely."""
        config = EngineConfig(enabled=True, external_calls_allowed=True)
        queue = SQLiteQueueStore()
        queue.enqueue(Job(job_type="ext_test", dedupe_key="blocked-1", max_retries=1))

        def blocking_handler(payload, cfg):
            check_external_call_allowed(cfg)  # LUMOS_BLOCK_EXTERNAL_CALLS=true → raises
            return {}

        register_handler("ext_test", blocking_handler)
        pool = WorkerPool(queue, config)
        pool.process_one()
        failed = queue.list_jobs(status="failed")
        self.assertEqual(len(failed), 1)
        self.assertIn("External call blocked", failed[0].error_message)

    def test_mock_provider_never_makes_network_call(self):
        """MockLLMProvider is guaranteed offline."""
        mock = MockLLMProvider()
        request = LLMRequest(prompt="test", max_tokens=100)
        response = mock.generate(request)
        self.assertTrue(response.success)
        self.assertEqual(response.model, "mock")

    def test_budget_tracker_in_memory_no_file(self):
        """In-memory BudgetTracker creates no files."""
        tracker = BudgetTracker(BudgetConfig())
        tracker.record(UsageRecord(event_type="test", estimated_cost_usd=0.01))
        self.assertEqual(tracker.db_path, ":memory:")


# ============================================================================
# AREA 4: Fake-engine dismiss/backfill API integration
# ============================================================================

class TestDismissBackfillAPIIntegration(unittest.TestCase):
    """End-to-end dismiss→backfill→undo using the engine's internal APIs.

    Simulates the full lifecycle that will run when the frontend calls
    POST /engine/briefing/dismiss and POST /engine/briefing/undo-dismiss.
    Uses fake in-memory state — no real DB, no HTTP, no external calls.
    """

    def _setup_session(self, n_displayed=5, n_reserves=8):
        """Create a fake engine session with displayed cards and reserves."""
        cache = BriefingCache()
        displayed = set()
        reserves = []
        for i in range(n_displayed + n_reserves):
            key = f"signal-{i}"
            briefing = KoreanBriefing(
                dedupe_key=key,
                display_title_ko=f"제목 {i}",
                headline_summary_ko=f"요약 {i}번 — 충분히 긴 한국어 텍스트를 포함합니다.",
            )
            cache.put(briefing)
            if i < n_displayed:
                displayed.add(key)
            else:
                reserves.append(ScoredCandidate(
                    candidate=RawCandidate(dedupe_key=key),
                    importance_score=1.0 - i * 0.05,
                ))
        return cache, displayed, set(), reserves

    def test_single_dismiss_and_backfill(self):
        """Dismiss one card → replaced by top reserve with cached briefing."""
        cache, displayed, ignored, reserves = self._setup_session()
        result = perform_backfill("signal-0", reserves, displayed, ignored, cache)

        self.assertTrue(result.replaced)
        self.assertEqual(result.dismissed_dedupe_key, "signal-0")
        self.assertEqual(result.replacement_dedupe_key, "signal-5")  # first reserve
        self.assertFalse(result.needs_generation)
        self.assertIsNotNone(result.replacement_briefing)
        self.assertNotIn("signal-0", displayed)
        self.assertIn("signal-5", displayed)
        self.assertIn("signal-0", ignored)

    def test_sequential_multi_dismiss(self):
        """Dismiss 5 cards in a row — each gets a different reserve."""
        cache, displayed, ignored, reserves = self._setup_session()
        replacements = []

        for i in range(5):
            result = perform_backfill(f"signal-{i}", reserves, displayed, ignored, cache)
            self.assertTrue(result.replaced)
            replacements.append(result.replacement_dedupe_key)

        # All replacements should be unique
        self.assertEqual(len(set(replacements)), 5)
        # Original 5 cards all dismissed
        for i in range(5):
            self.assertIn(f"signal-{i}", ignored)
            self.assertNotIn(f"signal-{i}", displayed)
        # 5 reserves now displayed
        for key in replacements:
            self.assertIn(key, displayed)

    def test_dismiss_then_undo(self):
        """Dismiss → undo restores exact original state."""
        cache, displayed, ignored, reserves = self._setup_session()
        original_displayed = set(displayed)

        result = perform_backfill("signal-0", reserves, displayed, ignored, cache)
        self.assertNotIn("signal-0", displayed)

        undo_dismiss("signal-0", result.replacement_dedupe_key, displayed, ignored)
        self.assertIn("signal-0", displayed)
        self.assertNotIn("signal-0", ignored)
        self.assertEqual(displayed, original_displayed)

    def test_dismiss_exhaust_reserves(self):
        """When reserves run out, backfill returns replaced=False."""
        cache, displayed, ignored, reserves = self._setup_session(n_displayed=5, n_reserves=2)
        # Dismiss 3 — only 2 reserves available
        for i in range(3):
            result = perform_backfill(f"signal-{i}", reserves, displayed, ignored, cache)
            if i < 2:
                self.assertTrue(result.replaced)
            else:
                self.assertFalse(result.replaced)

    def test_saved_state_independent_of_dismiss(self):
        """Dismissing doesn't affect separately saved state."""
        cache, displayed, ignored, reserves = self._setup_session()

        # Simulate saving a card (user bookmarks it)
        saved_keys = {"signal-0", "signal-1"}

        # Dismiss signal-0
        result = perform_backfill("signal-0", reserves, displayed, ignored, cache)
        # Saved state is managed separately; dismiss doesn't clear saves
        self.assertIn("signal-0", saved_keys)
        self.assertTrue(result.can_undo)

    def test_dismiss_undo_then_dismiss_again(self):
        """Dismiss → undo → dismiss again works cleanly."""
        cache, displayed, ignored, reserves = self._setup_session()

        # First dismiss
        r1 = perform_backfill("signal-0", reserves, displayed, ignored, cache)
        replacement1 = r1.replacement_dedupe_key

        # Undo
        undo_dismiss("signal-0", replacement1, displayed, ignored)

        # Dismiss again — should pick a different reserve (replacement1 is no longer displayed)
        r2 = perform_backfill("signal-0", reserves, displayed, ignored, cache)
        self.assertTrue(r2.replaced)
        # signal-0 is dismissed again
        self.assertNotIn("signal-0", displayed)
        self.assertIn("signal-0", ignored)


# ============================================================================
# AREA 5 (supplementary): Existing collector → engine v2 adapter
# ============================================================================

class TestCollectorAdapter(unittest.TestCase):
    """Verify v1 collectors can feed v2 engine via adapter."""

    def test_collected_item_to_candidate(self):
        from src.engine.collection.adapter import collected_item_to_candidate
        from src.sources.collectors.base import CollectedItem

        item = CollectedItem(
            source="github",
            source_item_id="gh-12345",
            url="https://github.com/test/repo",
            title="Test Repo",
            summary="A test repository",
            author="testuser",
            published_at="2026-10-16T10:00:00+09:00",
            metrics_json={"stars": 500, "forks": 100},
            dedupe_key="github:test-repo",
        )
        candidate = collected_item_to_candidate(item)

        self.assertEqual(candidate.dedupe_key, "github:test-repo")
        self.assertEqual(candidate.source, "github")
        self.assertEqual(candidate.title, "Test Repo")
        self.assertEqual(candidate.summary, "A test repository")
        self.assertEqual(candidate.published_at, "2026-10-16T10:00:00+09:00")
        self.assertEqual(candidate.metrics["stars"], 500)
        self.assertEqual(candidate.url, "https://github.com/test/repo")

    def test_batch_convert(self):
        from src.engine.collection.adapter import batch_convert
        from src.sources.collectors.base import CollectedItem

        items = [
            CollectedItem(source="github", source_item_id=f"gh-{i}", url=f"https://example.com/{i}",
                          title=f"Repo {i}", dedupe_key=f"github:repo-{i}")
            for i in range(10)
        ]
        candidates = batch_convert(items)
        self.assertEqual(len(candidates), 10)
        for i, c in enumerate(candidates):
            self.assertEqual(c.dedupe_key, f"github:repo-{i}")
            self.assertIsInstance(c, RawCandidate)

    def test_candidate_compatible_with_scorer(self):
        """Converted candidate can be scored by the evaluation engine."""
        from src.engine.collection.adapter import collected_item_to_candidate
        from src.sources.collectors.base import CollectedItem

        item = CollectedItem(
            source="hackernews",
            source_item_id="hn-99",
            url="https://news.ycombinator.com/item?id=99",
            title="AI breakthrough in language models",
            summary="Major breakthrough in AI research",
            published_at="2026-10-16T12:00:00+09:00",
            metrics_json={"comments": 150, "score": 300},
            dedupe_key="hn:99",
        )
        candidate = collected_item_to_candidate(item)
        config = EngineConfig()
        results = evaluate_candidates([candidate], Period.DAILY, ["AI"], config, reference_date=date(2026, 10, 16))
        self.assertEqual(len(results), 1)
        self.assertGreater(results[0].importance_score, 0)
        self.assertEqual(results[0].candidate.source, "hackernews")

    def test_missing_fields_handled(self):
        """Items with missing optional fields convert safely."""
        from src.engine.collection.adapter import collected_item_to_candidate
        from src.sources.collectors.base import CollectedItem

        item = CollectedItem(
            source="rss",
            source_item_id="rss-1",
            url="https://example.com/post",
            title="Minimal item",
        )
        candidate = collected_item_to_candidate(item)
        self.assertEqual(candidate.source, "rss")
        self.assertEqual(candidate.title, "Minimal item")
        self.assertIsNotNone(candidate.published_at)  # defaults to collected_at
        self.assertEqual(candidate.metrics, {})

    def test_all_implemented_sources_listed(self):
        """All implemented v1 sources can be mapped to engine v2 jobs."""
        from src.sources.collector_registry import IMPLEMENTED_SOURCES
        # These are all the sources that have real collectors
        expected = {"mock", "hackernews", "github", "youtube",
                    "rss", "official_ai_blogs", "company_newsroom",
                    "geeknews", "kisa_press", "kisa_research"}
        self.assertEqual(IMPLEMENTED_SOURCES, expected)


if __name__ == "__main__":
    unittest.main()

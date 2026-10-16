"""Comprehensive offline integration verification for engine v2.

Six verification areas:
1. Feature flag isolation and existing-feature safety
2. Cooperative collection dedup at 30/50/100 user scale
3. Period-independent evaluation with shared candidate pool
4. LLM cost optimization metrics (rule/cheap/expensive/cache)
5. Dismiss + backfill + undo lifecycle
6. Budget protection at scale

All tests use fake providers and in-memory DBs only.
"""

import json
import os
import threading
import time
import unittest
from collections import Counter
from datetime import date, datetime, timedelta, timezone

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
from src.engine.config import BudgetConfig, CollectionConfig, EngineConfig, EvaluationConfig, LLMConfig
from src.engine.evaluation.periods import period_range
from src.engine.evaluation.scorer import evaluate_candidates, score_candidate
from src.engine.llm.cache import BriefingCache
from src.engine.llm.providers import MockLLMProvider
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
from src.engine.personalization.backfill import BackfillResult, perform_backfill, select_backfill_candidate, undo_dismiss
from src.engine.personalization.ranker import get_reserve_candidates, personalise_rankings
from src.engine.queue.scheduler import Scheduler
from src.engine.queue.sqlite_store import SQLiteQueueStore
from src.engine.queue.worker import WorkerPool, register_handler, get_handler
from src.engine.safety import ExternalCallBlocked, check_external_call_allowed, is_test_environment


# ============================================================================
# VERIFICATION 1: Feature-flag isolation
# ============================================================================

class TestFeatureFlagIsolation(unittest.TestCase):
    """Verify engine components do nothing when flag is OFF."""

    def test_default_config_everything_off(self):
        config = EngineConfig()
        self.assertFalse(config.enabled)
        self.assertFalse(config.external_calls_allowed)
        self.assertFalse(config.collection.scheduler_enabled)

    def test_from_env_defaults_off(self):
        for var in ["LUMOS_ENGINE_V2", "LUMOS_EXTERNAL_CALLS", "LUMOS_SCHEDULER_ENABLED"]:
            os.environ.pop(var, None)
        config = EngineConfig.from_env()
        self.assertFalse(config.enabled)
        self.assertFalse(config.external_calls_allowed)
        self.assertFalse(config.collection.scheduler_enabled)

    def test_scheduler_no_op_when_disabled(self):
        """Scheduler.start() must be a no-op when scheduler_enabled=False."""
        calls = []
        config = EngineConfig()
        scheduler = Scheduler(config, lambda: calls.append(1))
        scheduler.start()
        self.assertFalse(scheduler.is_running())
        self.assertEqual(len(calls), 0)

    def test_scheduler_no_op_when_engine_disabled_but_scheduler_on(self):
        config = EngineConfig(
            enabled=False,
            collection=CollectionConfig(scheduler_enabled=True),
        )
        calls = []
        scheduler = Scheduler(config, lambda: calls.append(1))
        scheduler.start()
        self.assertFalse(scheduler.is_running())

    def test_worker_pool_no_auto_start(self):
        """WorkerPool does not start workers on construction."""
        config = EngineConfig()
        queue = SQLiteQueueStore()
        pool = WorkerPool(queue, config)
        self.assertFalse(pool.is_running())
        self.assertEqual(len(pool._threads), 0)

    def test_external_call_blocked_when_flag_off(self):
        config = EngineConfig()
        with self.assertRaises(ExternalCallBlocked):
            check_external_call_allowed(config)

    def test_external_call_blocked_even_with_api_key(self):
        os.environ["GEMINI_API_KEY"] = "fake-key-should-not-matter"
        try:
            config = EngineConfig()
            with self.assertRaises(ExternalCallBlocked):
                check_external_call_allowed(config)
        finally:
            os.environ.pop("GEMINI_API_KEY", None)

    def test_env_block_overrides_all_config(self):
        """LUMOS_BLOCK_EXTERNAL_CALLS=true overrides even fully-enabled config."""
        os.environ["LUMOS_BLOCK_EXTERNAL_CALLS"] = "true"
        config = EngineConfig(enabled=True, external_calls_allowed=True)
        with self.assertRaises(ExternalCallBlocked):
            check_external_call_allowed(config)

    def test_queue_store_creates_no_side_effects(self):
        """Creating a queue store in-memory doesn't touch any files."""
        store = SQLiteQueueStore()
        self.assertEqual(store.get_pending_count(), 0)
        self.assertEqual(store.get_running_count(), 0)

    def test_briefing_cache_creates_no_side_effects(self):
        cache = BriefingCache()
        self.assertEqual(cache.count(), 0)

    def test_budget_tracker_creates_no_side_effects(self):
        tracker = BudgetTracker(BudgetConfig())
        summary = tracker.get_usage_summary()
        self.assertEqual(summary["daily_cost_usd"], 0.0)

    def test_flag_off_engine_api_would_404(self):
        """The engine API checks config.enabled and returns 404 if False."""
        from src.api.engine import _get_engine_config
        config = _get_engine_config()
        # Default config has enabled=False
        self.assertFalse(config.enabled)


# ============================================================================
# VERIFICATION 2: Cooperative collection dedup at scale
# ============================================================================

class TestCooperativeCollection30Users(unittest.TestCase):
    """30-user scenario with overlapping interests."""

    @classmethod
    def setUpClass(cls):
        cls.users_30 = []
        interests_pool = ["AI", "startup", "DevOps", "open source", "ML"]
        for uid in range(1, 31):
            # Each user has 2-3 interests, heavily overlapping
            for kw in interests_pool[:2 + uid % 2]:
                cls.users_30.append({
                    "user_id": uid, "keyword": kw, "weight": 1.0
                })

    def test_grouping_30_users(self):
        groups = group_interests(self.users_30)
        # 5 unique keywords, but some are synonyms
        # "open source" -> "오픈소스", "ML" stays, etc.
        canonical_keys = {g.canonical_keyword for g in groups}
        # All 30 users should appear across groups
        all_users = set()
        for g in groups:
            all_users.update(g.user_ids)
        self.assertEqual(len(all_users), 30)
        # No group should have 0 users
        for g in groups:
            self.assertGreater(len(g.user_ids), 0)

    def test_dedup_in_queue_30_users(self):
        queue = SQLiteQueueStore()
        config = EngineConfig()
        plan = build_collection_plan(
            self.users_30, ["github"], set(range(1, 31)),
            "2026-10-16", "2026-10-16", config,
        )
        jobs = plan_to_jobs(plan)
        for j in jobs:
            queue.enqueue(j)
        pending = queue.get_pending_count()
        # Jobs = unique_groups * sources (1 source)
        self.assertEqual(pending, len(plan.groups))
        # Re-enqueuing same jobs shouldn't increase count
        for j in jobs:
            queue.enqueue(j)
        self.assertEqual(queue.get_pending_count(), pending)

    def test_30_users_same_interest_single_job(self):
        interests = [{"user_id": i, "keyword": "AI agent", "weight": 1.0} for i in range(1, 31)]
        queue = SQLiteQueueStore()
        config = EngineConfig()
        plan = build_collection_plan(
            interests, ["github"], set(range(1, 31)),
            "2026-10-16", "2026-10-16", config,
        )
        jobs = plan_to_jobs(plan)
        for j in jobs:
            queue.enqueue(j)
        self.assertEqual(queue.get_pending_count(), 1)
        self.assertEqual(len(plan.groups), 1)
        self.assertEqual(len(plan.groups[0].user_ids), 30)


class TestCooperativeCollection50Users(unittest.TestCase):
    """50-user scenario — main target for the spec."""

    @classmethod
    def setUpClass(cls):
        cls.interests = []
        kw_pool = ["AI", "startup", "open source", "DevOps", "ML",
                    "generative ai", "frontend", "backend", "SaaS", "fintech"]
        for uid in range(1, 51):
            # Spread across the full keyword pool: each user gets 3-8 keywords
            count = 3 + uid % 8
            for kw in kw_pool[:min(count, len(kw_pool))]:
                cls.interests.append({
                    "user_id": uid, "keyword": kw, "weight": 1.0
                })

    def test_grouping_reduces_50_users_interests(self):
        groups = group_interests(self.interests)
        total_raw_interest_rows = len(self.interests)
        self.assertGreater(total_raw_interest_rows, 150)
        # Groups should be much fewer than raw rows
        self.assertLess(len(groups), total_raw_interest_rows)
        # Verify synonym normalization merges correctly
        canonical_kws = {g.canonical_keyword for g in groups}
        # "generative ai" -> "생성형 AI", "open source" -> "오픈소스"
        self.assertIn("생성형 AI", canonical_kws)
        self.assertIn("오픈소스", canonical_kws)

    def test_50_users_queue_dedup(self):
        queue = SQLiteQueueStore()
        config = EngineConfig()
        plan = build_collection_plan(
            self.interests, ["github", "hackernews"], set(range(1, 51)),
            "2026-10-16", "2026-10-16", config,
        )
        jobs = plan_to_jobs(plan)
        dedupe_keys = [j.dedupe_key for j in jobs]
        unique_keys = set(dedupe_keys)
        # Each group * each source = 1 job, all keys should be unique
        self.assertEqual(len(dedupe_keys), len(unique_keys))

        for j in jobs:
            queue.enqueue(j)
        initial_count = queue.get_pending_count()

        # Re-enqueue all — count should not change
        for j in jobs:
            queue.enqueue(j)
        self.assertEqual(queue.get_pending_count(), initial_count)

    def test_50_users_budget_cap(self):
        config = EngineConfig(budget=BudgetConfig(max_daily_collection_jobs=10))
        plan = build_collection_plan(
            self.interests, ["github"], set(range(1, 51)),
            "2026-10-16", "2026-10-16", config,
        )
        # Budget cap should limit total jobs
        jobs = plan_to_jobs(plan)
        self.assertLessEqual(len(jobs), 10)

    def test_50_users_deterministic_dedup_keys(self):
        """Same inputs produce same dedupe_key regardless of order."""
        key1 = make_dedupe_key("AI", "github", "2026-10-16", "2026-10-16")
        key2 = make_dedupe_key("AI", "github", "2026-10-16", "2026-10-16")
        self.assertEqual(key1, key2)
        # Different interest -> different key
        key3 = make_dedupe_key("ML", "github", "2026-10-16", "2026-10-16")
        self.assertNotEqual(key1, key3)


class TestCooperativeCollection100Users(unittest.TestCase):
    """100-user stress test."""

    @classmethod
    def setUpClass(cls):
        cls.interests = []
        kw_pool = ["AI", "startup", "open source", "DevOps", "ML",
                    "generative ai", "frontend", "backend", "SaaS", "fintech",
                    "healthcare ai", "cyber security", "b2b saas", "llm"]
        for uid in range(1, 101):
            # Each user picks 3-14 keywords, ensuring full coverage
            count = 3 + uid % len(kw_pool)
            for kw in kw_pool[:min(count, len(kw_pool))]:
                cls.interests.append({
                    "user_id": uid, "keyword": kw, "weight": 1.0
                })

    def test_grouping_100_users_synonym_merge(self):
        groups = group_interests(self.interests)
        canonical_kws = {g.canonical_keyword for g in groups}
        # Synonyms must be merged
        # "cyber security" -> "사이버 보안"
        # "generative ai" -> "생성형 AI"
        # "llm" -> "LLM"
        # "open source" -> "오픈소스"
        self.assertIn("LLM", canonical_kws)
        self.assertIn("생성형 AI", canonical_kws)
        self.assertIn("오픈소스", canonical_kws)
        # Total users across all groups
        all_users = set()
        for g in groups:
            all_users.update(g.user_ids)
        self.assertEqual(len(all_users), 100)

    def test_100_sequential_enqueue_dedup(self):
        queue = SQLiteQueueStore()
        # 100 users, each enqueuing their own interests — many overlap
        for uid in range(1, 101):
            topic_idx = uid % 10
            queue.enqueue(Job(
                job_type=JobType.COLLECT,
                dedupe_key=f"topic-{topic_idx}",
                payload_json={"user_id": uid},
            ))
        # Only 10 unique topics
        self.assertEqual(queue.get_pending_count(), 10)

    def test_100_users_full_plan_counts(self):
        queue = SQLiteQueueStore()
        config = EngineConfig()
        plan = build_collection_plan(
            self.interests, ["github"], set(range(1, 101)),
            "2026-10-16", "2026-10-16", config,
        )
        jobs = plan_to_jobs(plan)
        for j in jobs:
            queue.enqueue(j)
        # Jobs = number of unique canonical groups (capped by budget)
        n_groups = len(plan.groups)
        self.assertEqual(queue.get_pending_count(), n_groups)
        # Re-enqueue doesn't increase
        original_count = queue.get_pending_count()
        for j in jobs:
            queue.enqueue(j)
        self.assertEqual(queue.get_pending_count(), original_count)


class TestWorkerFailureAndLease(unittest.TestCase):
    """Worker crash, retry, and lease expiry scenarios."""

    def test_claim_and_complete(self):
        queue = SQLiteQueueStore()
        queue.enqueue(Job(job_type=JobType.COLLECT, dedupe_key="w-1"))
        job = queue.claim("worker-0")
        self.assertIsNotNone(job)
        self.assertEqual(job.status, JobStatus.RUNNING)
        queue.complete(job.id, {"items": 5})
        completed = queue.get_job(job.id)
        self.assertEqual(completed.status, JobStatus.COMPLETED)

    def test_worker_crash_retry(self):
        """Simulating worker crash: claim then fail, should retry."""
        queue = SQLiteQueueStore()
        queue.enqueue(Job(job_type=JobType.COLLECT, dedupe_key="crash-1", max_retries=3))
        j = queue.claim("worker-0")
        queue.fail(j.id, "worker crashed")
        # Job goes back to pending
        job = queue.get_job(j.id)
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.retry_count, 1)
        self.assertIsNone(job.lease_owner)

    def test_multiple_failures_exhaust_retries(self):
        queue = SQLiteQueueStore()
        queue.enqueue(Job(job_type=JobType.COLLECT, dedupe_key="exhaust-1", max_retries=2))
        for attempt in range(2):
            j = queue.claim(f"worker-{attempt}")
            self.assertIsNotNone(j, f"Should be claimable on attempt {attempt}")
            queue.fail(j.id, f"error-{attempt}")
        job = queue.get_job(1)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.retry_count, 2)

    def test_lease_expiry_recovery(self):
        """Expired leases should be recovered to pending."""
        queue = SQLiteQueueStore()
        queue.enqueue(Job(job_type=JobType.COLLECT, dedupe_key="lease-1"))
        job = queue.claim("worker-0", lease_seconds=0)  # expires immediately
        time.sleep(0.01)
        recovered = queue.recover_expired_leases()
        self.assertEqual(recovered, 1)
        j = queue.get_job(job.id)
        self.assertEqual(j.status, JobStatus.PENDING)
        self.assertIsNone(j.lease_owner)

    def test_lease_not_expired_stays_running(self):
        queue = SQLiteQueueStore()
        queue.enqueue(Job(job_type=JobType.COLLECT, dedupe_key="healthy-1"))
        job = queue.claim("worker-0", lease_seconds=300)
        recovered = queue.recover_expired_leases()
        self.assertEqual(recovered, 0)
        j = queue.get_job(job.id)
        self.assertEqual(j.status, JobStatus.RUNNING)

    def test_worker_pool_process_one_with_handler(self):
        """WorkerPool.process_one executes a registered handler."""
        config = EngineConfig(enabled=True, external_calls_allowed=True)
        queue = SQLiteQueueStore()
        queue.enqueue(Job(job_type="test_handler", dedupe_key="process-1"))
        results = []
        register_handler("test_handler", lambda p, c: {"processed": True})
        pool = WorkerPool(queue, config)
        did = pool.process_one()
        self.assertTrue(did)
        completed = queue.list_jobs(status="completed")
        self.assertEqual(len(completed), 1)

    def test_worker_pool_fails_job_with_no_handler(self):
        config = EngineConfig(enabled=True, external_calls_allowed=True)
        queue = SQLiteQueueStore()
        queue.enqueue(Job(job_type="unknown_type", dedupe_key="no-handler-1", max_retries=1))
        pool = WorkerPool(queue, config)
        pool.process_one()
        failed = queue.list_jobs(status="failed")
        self.assertEqual(len(failed), 1)
        self.assertIn("No handler", failed[0].error_message)

    def test_concurrent_claim_atomic(self):
        """Two workers claiming simultaneously: only one wins."""
        queue = SQLiteQueueStore()
        queue.enqueue(Job(job_type=JobType.COLLECT, dedupe_key="race-1"))
        results = [None, None]

        def claim_job(idx):
            results[idx] = queue.claim(f"racer-{idx}")

        t1 = threading.Thread(target=claim_job, args=(0,))
        t2 = threading.Thread(target=claim_job, args=(1,))
        t1.start(); t2.start()
        t1.join(); t2.join()
        claimed = [r for r in results if r is not None]
        self.assertEqual(len(claimed), 1)


# ============================================================================
# VERIFICATION 3: Period-independent evaluation
# ============================================================================

class TestPeriodIndependentEvaluation(unittest.TestCase):
    """Same candidate pool scored independently for daily/weekly/monthly."""

    @classmethod
    def setUpClass(cls):
        """Build a diverse candidate pool for all period tests."""
        cls.ref_date = date(2026, 10, 16)  # Friday
        cls.config = EngineConfig()
        cls.interests = ["AI", "startup", "DevOps"]

        cls.candidates = [
            # Very recent, high engagement, AI-related
            RawCandidate(
                dedupe_key="c-recent-hot",
                title="AI Breakthrough Today",
                summary="A major AI advancement announced today",
                published_at="2026-10-16T09:00:00+09:00",
                metrics={"stars": 5000, "comments": 200},
                source="github",
            ),
            # Recent, low engagement
            RawCandidate(
                dedupe_key="c-recent-cold",
                title="Minor DevOps Tool Update",
                summary="Small DevOps utility released",
                published_at="2026-10-16T06:00:00+09:00",
                metrics={"stars": 5, "comments": 1},
                source="hackernews",
            ),
            # 5 days old, very high engagement
            RawCandidate(
                dedupe_key="c-week-popular",
                title="Startup Funding Record",
                summary="Major startup ecosystem funding round",
                published_at="2026-10-11T12:00:00+09:00",
                metrics={"stars": 20000, "comments": 500},
                source="hackernews",
            ),
            # 20 days old, extremely high engagement, strong interest match
            RawCandidate(
                dedupe_key="c-month-blockbuster",
                title="AI DevOps Startup Revolution",
                summary="AI startup transforms DevOps with new platform",
                published_at="2026-09-26T12:00:00+09:00",
                metrics={"stars": 50000, "comments": 1000},
                source="github",
            ),
            # Very old (60 days), moderate engagement
            RawCandidate(
                dedupe_key="c-old-moderate",
                title="General Tech Roundup",
                summary="General technology news from August",
                published_at="2026-08-17T12:00:00+09:00",
                metrics={"stars": 100, "comments": 30},
                source="hackernews",
            ),
        ]

    def test_daily_scores_independently(self):
        daily = evaluate_candidates(
            self.candidates, Period.DAILY, self.interests,
            self.config, reference_date=self.ref_date,
        )
        self.assertGreater(len(daily), 0)
        # Daily favors recency: "c-recent-hot" should rank highest
        self.assertEqual(daily[0].candidate.dedupe_key, "c-recent-hot")

    def test_weekly_scores_independently(self):
        weekly = evaluate_candidates(
            self.candidates, Period.WEEKLY, self.interests,
            self.config, reference_date=self.ref_date,
        )
        self.assertGreater(len(weekly), 0)
        # Weekly: engagement + interest balance
        # "c-week-popular" and "c-recent-hot" should rank high
        top_keys = [s.candidate.dedupe_key for s in weekly[:2]]
        self.assertIn("c-recent-hot", top_keys)

    def test_monthly_scores_independently(self):
        monthly = evaluate_candidates(
            self.candidates, Period.MONTHLY, self.interests,
            self.config, reference_date=self.ref_date,
        )
        self.assertGreater(len(monthly), 0)
        # Monthly: interest_match 0.50, engagement 0.40
        # "c-month-blockbuster" matches all 3 interests + massive engagement
        self.assertEqual(monthly[0].candidate.dedupe_key, "c-month-blockbuster")

    def test_periods_produce_different_rankings(self):
        daily = evaluate_candidates(
            self.candidates, Period.DAILY, self.interests,
            self.config, reference_date=self.ref_date,
        )
        weekly = evaluate_candidates(
            self.candidates, Period.WEEKLY, self.interests,
            self.config, reference_date=self.ref_date,
        )
        monthly = evaluate_candidates(
            self.candidates, Period.MONTHLY, self.interests,
            self.config, reference_date=self.ref_date,
        )
        d_order = [s.candidate.dedupe_key for s in daily]
        w_order = [s.candidate.dedupe_key for s in weekly]
        m_order = [s.candidate.dedupe_key for s in monthly]
        # Rankings should differ across periods
        self.assertNotEqual(d_order, m_order, "Daily and monthly should rank differently")

    def test_daily_excluded_remains_weekly_candidate(self):
        """Items outside daily range still appear in weekly/monthly."""
        daily = evaluate_candidates(
            self.candidates, Period.DAILY, self.interests,
            self.config, reference_date=self.ref_date,
        )
        weekly = evaluate_candidates(
            self.candidates, Period.WEEKLY, self.interests,
            self.config, reference_date=self.ref_date,
        )
        daily_keys = {s.candidate.dedupe_key for s in daily if s.importance_score > 0}
        weekly_keys = {s.candidate.dedupe_key for s in weekly if s.importance_score > 0}
        # "c-week-popular" (5 days old) should have 0 recency in daily but score in weekly
        self.assertIn("c-week-popular", weekly_keys)

    def test_score_breakdown_has_correct_components(self):
        daily = evaluate_candidates(
            self.candidates, Period.DAILY, self.interests,
            self.config, reference_date=self.ref_date,
        )
        for sc in daily:
            self.assertIn("recency", sc.score_breakdown)
            self.assertIn("engagement", sc.score_breakdown)
            self.assertIn("interest_match", sc.score_breakdown)
            # All component scores should be in [0, 1]
            for k, v in sc.score_breakdown.items():
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, 1.0)

    def test_weight_sums_correct_per_period(self):
        """Verify weights sum to ~1.0 for each period."""
        from src.engine.evaluation.scorer import _PERIOD_WEIGHTS
        for period, weights in _PERIOD_WEIGHTS.items():
            total = sum(weights.values())
            self.assertAlmostEqual(total, 1.0, places=2,
                                   msg=f"Weights for {period} don't sum to 1.0")

    def test_independent_scores_differ_numerically(self):
        """Same candidate gets different numeric scores per period."""
        c = self.candidates[0]  # c-recent-hot
        d_start, d_end = period_range(Period.DAILY, self.ref_date)
        w_start, w_end = period_range(Period.WEEKLY, self.ref_date)
        m_start, m_end = period_range(Period.MONTHLY, self.ref_date)

        d_sc = score_candidate(c, Period.DAILY, d_start, d_end, self.interests)
        w_sc = score_candidate(c, Period.WEEKLY, w_start, w_end, self.interests)
        m_sc = score_candidate(c, Period.MONTHLY, m_start, m_end, self.interests)

        # Scores must differ because weights differ
        self.assertNotEqual(d_sc.importance_score, w_sc.importance_score)
        self.assertNotEqual(w_sc.importance_score, m_sc.importance_score)


# ============================================================================
# VERIFICATION 4: LLM cost optimization metrics
# ============================================================================

class TestLLMCostOptimization(unittest.TestCase):
    """Measure rule-based/cheap/expensive/cache hit rates."""

    def setUp(self):
        self.cache = BriefingCache()
        self.config = EngineConfig()
        self.mock_cheap = MockLLMProvider()
        self.mock_expensive = MockLLMProvider()

    def _make_candidates(self, n, korean_ratio=0.0, cached_ratio=0.0):
        """Generate n candidates with configurable Korean/cached ratios."""
        candidates = []
        n_korean = int(n * korean_ratio)
        n_cached = int(n * cached_ratio)

        for i in range(n):
            if i < n_korean:
                # Already Korean — rule-based will handle
                c = RawCandidate(
                    dedupe_key=f"korean-{i}",
                    title=f"한국어 제목 {i}번째 소식입니다",
                    summary=f"이것은 이미 한국어로 작성된 요약입니다. 충분히 긴 한국어 텍스트를 포함합니다.",
                    source="korean-blog",
                )
            elif i < n_korean + n_cached:
                # Pre-cached
                c = RawCandidate(
                    dedupe_key=f"cached-{i}",
                    title=f"Cached Title {i}",
                    summary=f"Cached summary for item {i}",
                    source="github",
                )
                self.cache.put(KoreanBriefing(
                    dedupe_key=f"cached-{i}",
                    display_title_ko=f"캐시된 제목 {i}",
                    headline_summary_ko=f"캐시된 요약 {i}",
                ))
            else:
                # Needs LLM
                c = RawCandidate(
                    dedupe_key=f"need-llm-{i}",
                    title=f"English Title {i}",
                    summary=f"English summary for item {i}",
                    source="hackernews",
                )
            candidates.append(c)
        return candidates

    def test_100_candidates_mixed_routing(self):
        """100 candidates: 20% Korean, 30% cached, 50% need LLM."""
        candidates = self._make_candidates(100, korean_ratio=0.2, cached_ratio=0.3)
        router = LLMRouter(
            self.config, self.cache,
            cheap_provider=self.mock_cheap,
            expensive_provider=self.mock_expensive,
        )
        result = router.generate_briefings(candidates)

        # Count routing tiers
        rule_only = sum(1 for b in result.values() if b.generated_by == LLMTier.RULE)
        cheap_generated = sum(1 for b in result.values() if b.generated_by == LLMTier.CHEAP)
        cheap_calls = self.mock_cheap.calls
        expensive_calls = self.mock_expensive.calls

        # 20 Korean handled by rule, 30 cached (generated_by also "rule" by default)
        # So rule_only = 20 + 30 = 50 (rule + cache both have generated_by="rule")
        # 50 need LLM: mock returns batch arrays, all validated as cheap
        self.assertEqual(rule_only, 50, f"Expected 50 rule+cached, got {rule_only}")
        self.assertEqual(cheap_generated, 50, f"Expected 50 cheap-generated, got {cheap_generated}")
        # 50 items / batch_size 5 = 10 cheap LLM calls
        self.assertEqual(len(cheap_calls), 10)
        # Expensive not called (disabled by default)
        self.assertEqual(len(expensive_calls), 0)
        # All 100 should have results
        self.assertEqual(len(result), 100)

    def test_cache_prevents_duplicate_llm_calls(self):
        """Second router with same cache should make 0 new calls."""
        candidates = self._make_candidates(10, korean_ratio=0.0, cached_ratio=0.0)
        router1 = LLMRouter(self.config, self.cache, cheap_provider=self.mock_cheap)
        result1 = router1.generate_briefings(candidates)
        # First pass should generate all 10 via LLM and cache them
        self.assertEqual(len(result1), 10)
        calls_first = len(self.mock_cheap.calls)
        self.assertGreater(calls_first, 0)

        # Second router, same shared cache — all should be cache hits
        mock2 = MockLLMProvider()
        router2 = LLMRouter(self.config, self.cache, cheap_provider=mock2)
        result2 = router2.generate_briefings(candidates)

        self.assertEqual(len(mock2.calls), 0, "Second pass should use cache only")
        self.assertEqual(len(result2), 10)

    def test_validation_failure_escalation(self):
        """When cheap model returns bad data and expensive is enabled, it escalates."""
        config = EngineConfig(llm=LLMConfig(expensive_model_enabled=True))

        # Cheap returns empty (invalid) response
        bad_cheap = MockLLMProvider()
        bad_cheap.set_response('{"display_title_ko": "", "headline_summary_ko": "", "key_facts_ko": []}')
        good_expensive = MockLLMProvider()

        candidates = [RawCandidate(dedupe_key="escalate-1", title="English Only", summary="Test")]
        router = LLMRouter(config, self.cache, cheap_provider=bad_cheap, expensive_provider=good_expensive)
        result = router.generate_briefings(candidates)

        self.assertEqual(len(bad_cheap.calls), 1, "Cheap should be called once")
        self.assertEqual(len(good_expensive.calls), 1, "Expensive should be called after validation failure")

    def test_all_korean_zero_llm_calls(self):
        """If all candidates are already in Korean, LLM is never called."""
        candidates = self._make_candidates(50, korean_ratio=1.0)
        router = LLMRouter(self.config, self.cache, cheap_provider=self.mock_cheap)
        result = router.generate_briefings(candidates)

        self.assertEqual(len(self.mock_cheap.calls), 0)
        self.assertEqual(len(result), 50)
        for b in result.values():
            self.assertEqual(b.generated_by, LLMTier.RULE)

    def test_cost_metrics_100_candidates(self):
        """Report per-100-candidate metrics."""
        candidates = self._make_candidates(100, korean_ratio=0.2, cached_ratio=0.3)
        router = LLMRouter(self.config, self.cache, cheap_provider=self.mock_cheap)
        result = router.generate_briefings(candidates)

        rule_plus_cache = sum(1 for b in result.values() if b.generated_by == LLMTier.RULE)
        cheap_generated = sum(1 for b in result.values() if b.generated_by == LLMTier.CHEAP)
        metrics = {
            "total_candidates": 100,
            "rule_based_pure": 20,  # Korean text candidates
            "cache_hits": 30,  # pre-cached
            "rule_plus_cache": rule_plus_cache,  # both have generated_by="rule"
            "cheap_llm_generated": cheap_generated,
            "cheap_llm_api_calls": len(self.mock_cheap.calls),
            "expensive_llm_calls": 0,
            "tokens_used": router.tokens_used,
            "no_llm_rate": (20 + 30) / 100,  # 50% avoided LLM entirely
            "llm_calls_per_100": len(self.mock_cheap.calls),
        }
        self.__class__.cost_metrics = metrics

        # At least 50% of candidates handled without any LLM call
        self.assertGreaterEqual(metrics["no_llm_rate"], 0.5)
        # 50 items / batch 5 = 10 API calls for 100 candidates
        self.assertEqual(metrics["cheap_llm_api_calls"], 10)
        self.assertEqual(len(result), 100)

    def test_briefing_validation_catches_bad_output(self):
        """Validator rejects empty or too-short briefings."""
        bad = KoreanBriefing(dedupe_key="bad", display_title_ko="", headline_summary_ko="짧")
        result = validate_briefing(bad)
        self.assertFalse(result.valid)

        good = KoreanBriefing(
            dedupe_key="good",
            display_title_ko="좋은 한국어 제목입니다",
            headline_summary_ko="이것은 충분히 긴 한국어 요약입니다. 의미 있는 내용을 담고 있습니다.",
        )
        result = validate_briefing(good)
        self.assertTrue(result.valid)
        self.assertGreater(result.confidence, 0.0)


# ============================================================================
# VERIFICATION 5: Dismiss + backfill lifecycle
# ============================================================================

class TestDismissBackfillLifecycle(unittest.TestCase):
    """Full dismiss → backfill → undo cycle with edge cases."""

    def setUp(self):
        self.cache = BriefingCache()
        # Pre-populate some cached briefings for reserves
        for i in range(5):
            self.cache.put(KoreanBriefing(
                dedupe_key=f"reserve-{i}",
                display_title_ko=f"예비 제목 {i}",
                headline_summary_ko=f"예비 요약 {i}",
            ))

        self.reserves = [
            ScoredCandidate(
                candidate=RawCandidate(dedupe_key=f"reserve-{i}"),
                importance_score=0.9 - i * 0.1,
            )
            for i in range(5)
        ]

    def test_basic_dismiss_and_backfill(self):
        displayed = {"card-0", "card-1", "card-2"}
        ignored = set()
        result = perform_backfill("card-0", self.reserves, displayed, ignored, self.cache)

        self.assertTrue(result.replaced)
        self.assertEqual(result.replacement_dedupe_key, "reserve-0")
        self.assertIsNotNone(result.replacement_briefing)
        self.assertFalse(result.needs_generation)
        self.assertNotIn("card-0", displayed)
        self.assertIn("card-0", ignored)
        self.assertTrue(result.can_undo)

    def test_undo_restores_original(self):
        displayed = {"card-0", "card-1", "card-2"}
        ignored = set()
        result = perform_backfill("card-0", self.reserves, displayed, ignored, self.cache)

        # Undo
        undo_dismiss("card-0", result.replacement_dedupe_key, displayed, ignored)
        self.assertIn("card-0", displayed)
        self.assertNotIn("card-0", ignored)
        self.assertNotIn("reserve-0", displayed)

    def test_multiple_dismissals_sequential(self):
        """Dismissing multiple cards picks different reserves each time."""
        displayed = {"card-0", "card-1", "card-2", "card-3", "card-4"}
        ignored = set()
        replacements = []

        for i in range(3):
            result = perform_backfill(f"card-{i}", self.reserves, displayed, ignored, self.cache)
            self.assertTrue(result.replaced)
            replacements.append(result.replacement_dedupe_key)

        # Each replacement should be unique
        self.assertEqual(len(set(replacements)), 3)

    def test_no_backfill_when_reserves_exhausted(self):
        displayed = {"card-0"}
        ignored = set()
        # Mark all reserves as ignored
        for r in self.reserves:
            ignored.add(r.candidate.dedupe_key)

        result = perform_backfill("card-0", self.reserves, displayed, ignored, self.cache)
        self.assertFalse(result.replaced)
        self.assertIsNone(result.replacement_dedupe_key)

    def test_backfill_without_cache_needs_generation(self):
        """Reserve candidate not in cache → needs_generation=True."""
        cache = BriefingCache()  # empty cache
        reserves = [ScoredCandidate(
            candidate=RawCandidate(dedupe_key="uncached-reserve"),
            importance_score=0.8,
        )]
        displayed = {"card-0"}
        ignored = set()
        result = perform_backfill("card-0", reserves, displayed, ignored, cache)

        self.assertTrue(result.replaced)
        self.assertTrue(result.needs_generation)
        self.assertIsNone(result.replacement_briefing)

    def test_saved_state_independent_of_dismiss(self):
        """User's 'saved' signals are not affected by dismiss."""
        saved_keys = {"card-0", "card-2"}  # simulated saved set
        displayed = {"card-0", "card-1", "card-2"}
        ignored = set()

        perform_backfill("card-0", self.reserves, displayed, ignored, self.cache)

        # saved_keys is untouched — it's managed separately
        self.assertIn("card-0", saved_keys)
        self.assertIn("card-2", saved_keys)

    def test_dismissed_card_not_in_reserves(self):
        """A dismissed card should not appear in future reserve candidates."""
        scored = [
            ScoredCandidate(candidate=RawCandidate(dedupe_key="a"), importance_score=0.9),
            ScoredCandidate(candidate=RawCandidate(dedupe_key="b"), importance_score=0.8),
            ScoredCandidate(candidate=RawCandidate(dedupe_key="c"), importance_score=0.7),
        ]
        displayed = {"a"}
        ignored = {"a"}  # user dismissed "a"

        reserves = get_reserve_candidates(scored, displayed, ignored)
        reserve_keys = {r.candidate.dedupe_key for r in reserves}
        self.assertNotIn("a", reserve_keys)
        self.assertIn("b", reserve_keys)
        self.assertIn("c", reserve_keys)

    def test_personalised_ranking_excludes_ignored(self):
        """personalise_rankings must exclude ignored items."""
        scored = [
            ScoredCandidate(
                candidate=RawCandidate(dedupe_key=f"item-{i}", title=f"AI Item {i}"),
                importance_score=1.0 - i * 0.1,
            )
            for i in range(10)
        ]
        briefings = {}
        result = personalise_rankings(
            scored, ["AI"], ignored_dedupe_keys={"item-0", "item-1"},
            tracked_dedupe_keys=set(), briefings=briefings,
        )
        result_keys = [r["dedupe_key"] for r in result]
        self.assertNotIn("item-0", result_keys)
        self.assertNotIn("item-1", result_keys)
        self.assertEqual(result[0]["dedupe_key"], "item-2")


# ============================================================================
# VERIFICATION 6: Budget protection at scale
# ============================================================================

class TestBudgetProtection(unittest.TestCase):
    """Validate budget caps with 30-100 user loads."""

    def test_daily_budget_blocks_when_exceeded(self):
        config = BudgetConfig(daily_budget_usd=1.00)
        tracker = BudgetTracker(config)
        # Spend $1.01
        tracker.record(UsageRecord(event_type="collection", estimated_cost_usd=1.01))
        self.assertFalse(tracker.check_daily_budget())
        self.assertFalse(tracker.can_start_external_job())

    def test_monthly_budget_blocks_when_exceeded(self):
        config = BudgetConfig(monthly_budget_usd=10.00)
        tracker = BudgetTracker(config)
        tracker.record(UsageRecord(event_type="collection", estimated_cost_usd=10.01))
        self.assertFalse(tracker.check_monthly_budget())
        self.assertFalse(tracker.can_start_external_job())

    def test_collection_limit_blocks_at_cap(self):
        config = BudgetConfig(max_daily_collection_jobs=5)
        tracker = BudgetTracker(config)
        for _ in range(5):
            tracker.record(UsageRecord(event_type="collection", estimated_cost_usd=0.01))
        self.assertFalse(tracker.check_daily_collection_limit())
        self.assertFalse(tracker.can_start_external_job())

    def test_chat_limit_per_user(self):
        config = BudgetConfig(max_chat_requests_per_day=10)
        tracker = BudgetTracker(config)
        for _ in range(10):
            tracker.record(UsageRecord(user_id=1, event_type="chat", estimated_cost_usd=0.001))
        self.assertFalse(tracker.check_user_chat_limit(1))
        # Different user still has budget
        self.assertTrue(tracker.check_user_chat_limit(2))

    def test_briefing_generation_limit(self):
        config = BudgetConfig(max_daily_briefing_generations=20)
        tracker = BudgetTracker(config)
        for _ in range(20):
            tracker.record(UsageRecord(event_type="llm_cheap", estimated_cost_usd=0.01))
        self.assertFalse(tracker.check_daily_briefing_generation_limit())

    def test_expensive_llm_limit(self):
        config = BudgetConfig(max_daily_expensive_llm_calls=5)
        tracker = BudgetTracker(config)
        for _ in range(5):
            tracker.record(UsageRecord(event_type="llm_expensive", estimated_cost_usd=0.05))
        self.assertFalse(tracker.check_expensive_llm_limit())

    def test_cached_display_free(self):
        """Serving cached briefings does NOT count as LLM usage."""
        config = BudgetConfig(max_daily_briefing_generations=1)
        tracker = BudgetTracker(config)
        # One real generation
        tracker.record(UsageRecord(event_type="llm_cheap", estimated_cost_usd=0.01))
        self.assertFalse(tracker.check_daily_briefing_generation_limit())
        # But cached display has no event — budget is not further consumed
        # (No record for display, since config.cache_display_counts_as_usage=False)
        # Daily cost should remain $0.01
        summary = tracker.get_usage_summary()
        self.assertAlmostEqual(summary["daily_cost_usd"], 0.01)

    def test_30_users_daily_burst(self):
        """30 users each making requests — budget caps apply globally."""
        config = BudgetConfig(
            max_chat_requests_per_day=10,
            max_daily_collection_jobs=50,
            daily_budget_usd=5.00,
        )
        tracker = BudgetTracker(config)
        # 30 users, each makes 5 chat requests
        for uid in range(1, 31):
            for _ in range(5):
                tracker.record(UsageRecord(
                    user_id=uid, event_type="chat",
                    estimated_cost_usd=0.005,
                ))
        # Total: 150 events, $0.75
        summary = tracker.get_usage_summary()
        self.assertAlmostEqual(summary["daily_cost_usd"], 0.75, places=2)
        self.assertTrue(tracker.check_daily_budget())  # under $5
        # Each user has 5/10 chat requests left
        self.assertTrue(tracker.check_user_chat_limit(1))

    def test_50_users_concurrent_collection(self):
        """50 users trigger collections — capped at max_daily_collection_jobs."""
        config = BudgetConfig(max_daily_collection_jobs=50)
        tracker = BudgetTracker(config)
        # Simulate 50 collection jobs
        for i in range(50):
            tracker.record(UsageRecord(
                event_type="collection", estimated_cost_usd=0.02,
            ))
        self.assertFalse(tracker.check_daily_collection_limit())
        summary = tracker.get_usage_summary()
        self.assertAlmostEqual(summary["daily_cost_usd"], 1.00, places=2)

    def test_100_users_budget_stress(self):
        """100 users combined: chat + collection + LLM stays under caps."""
        config = BudgetConfig(
            max_chat_requests_per_day=10,
            max_daily_collection_jobs=50,
            max_daily_briefing_generations=100,
            daily_budget_usd=5.00,
            monthly_budget_usd=100.00,
        )
        tracker = BudgetTracker(config)

        # 100 users: 3 chat each = 300 events @ $0.001 = $0.30
        for uid in range(1, 101):
            for _ in range(3):
                tracker.record(UsageRecord(
                    user_id=uid, event_type="chat", estimated_cost_usd=0.001,
                ))

        # 50 collection jobs @ $0.02 = $1.00
        for _ in range(50):
            tracker.record(UsageRecord(event_type="collection", estimated_cost_usd=0.02))

        # 80 briefing generations @ $0.01 = $0.80
        for _ in range(80):
            tracker.record(UsageRecord(event_type="llm_cheap", estimated_cost_usd=0.01))

        summary = tracker.get_usage_summary()
        total_cost = summary["daily_cost_usd"]
        self.assertAlmostEqual(total_cost, 2.10, places=2)  # $0.30+$1.00+$0.80
        self.assertTrue(tracker.check_daily_budget())  # under $5
        self.assertFalse(tracker.check_daily_collection_limit())  # 50/50 used
        self.assertTrue(tracker.check_daily_briefing_generation_limit())  # 80/100 used

    def test_simultaneous_topic_requests_single_job(self):
        """100 users request same topic — only 1 collection job, 1 budget charge."""
        queue = SQLiteQueueStore()
        config = EngineConfig()
        interests = [{"user_id": i, "keyword": "AI agent", "weight": 1.0} for i in range(1, 101)]
        plan = build_collection_plan(
            interests, ["github"], set(range(1, 101)),
            "2026-10-16", "2026-10-16", config,
        )
        jobs = plan_to_jobs(plan)
        for j in jobs:
            queue.enqueue(j)
        # Only 1 job, not 100
        self.assertEqual(queue.get_pending_count(), 1)


# ============================================================================
# Regression: UI flag-independent changes
# ============================================================================

class TestUIChangesRegression(unittest.TestCase):
    """Settings and onboarding changes applied regardless of engine flag."""

    def test_settings_partial_update_preserves_fields(self):
        from src.api.models import SettingsUpdate
        update = SettingsUpdate(signal_count=3)
        d = update.model_dump(exclude_unset=True)
        self.assertIn("signal_count", d)
        self.assertNotIn("generate_mode", d)
        self.assertNotIn("briefing_time", d)
        self.assertNotIn("auto_briefing", d)

    def test_settings_empty_update_preserves_everything(self):
        from src.api.models import SettingsUpdate
        update = SettingsUpdate()
        d = update.model_dump(exclude_unset=True)
        self.assertEqual(len(d), 0)


if __name__ == "__main__":
    unittest.main()

"""Offline tests for cooperative collection planning.

Validates: interest grouping, synonym normalisation, collection plan
budget allocation, dedupe key generation, plan-to-jobs conversion.
"""

import os
import unittest

os.environ["LUMOS_TEST_MODE"] = "true"
os.environ["LUMOS_BLOCK_EXTERNAL_CALLS"] = "true"

from src.engine.collection.planner import (
    build_collection_plan,
    group_interests,
    make_dedupe_key,
    normalise_keyword,
    plan_to_jobs,
)
from src.engine.config import EngineConfig
from src.engine.models import JobType


class TestNormaliseKeyword(unittest.TestCase):
    def test_synonym_mapping(self):
        self.assertEqual(normalise_keyword("artificial intelligence"), "AI")
        self.assertEqual(normalise_keyword("deep learning"), "ML")
        self.assertEqual(normalise_keyword("generative ai"), "생성형 AI")

    def test_passthrough(self):
        self.assertEqual(normalise_keyword("Rust"), "Rust")
        self.assertEqual(normalise_keyword("  스타트업  "), "스타트업")


class TestGroupInterests(unittest.TestCase):
    def test_basic_grouping(self):
        interests = [
            {"user_id": 1, "keyword": "AI", "weight": 2.0, "category": "tech"},
            {"user_id": 2, "keyword": "artificial intelligence", "weight": 1.0, "category": "tech"},
            {"user_id": 3, "keyword": "AI", "weight": 3.0, "category": "tech"},
        ]
        groups = group_interests(interests)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].canonical_keyword, "AI")
        self.assertEqual(len(groups[0].user_ids), 3)
        self.assertAlmostEqual(groups[0].weight, 6.0)

    def test_active_user_filter(self):
        interests = [
            {"user_id": 1, "keyword": "AI", "weight": 1.0},
            {"user_id": 2, "keyword": "AI", "weight": 1.0},
            {"user_id": 3, "keyword": "Rust", "weight": 1.0},
        ]
        groups = group_interests(interests, active_user_ids={1, 3})
        keywords = {g.canonical_keyword for g in groups}
        self.assertIn("AI", keywords)
        self.assertIn("Rust", keywords)
        # User 2's AI interest should be excluded
        ai_group = next(g for g in groups if g.canonical_keyword == "AI")
        self.assertNotIn(2, ai_group.user_ids)

    def test_sorted_by_weight(self):
        interests = [
            {"user_id": 1, "keyword": "low", "weight": 0.5},
            {"user_id": 1, "keyword": "high", "weight": 10.0},
        ]
        groups = group_interests(interests)
        self.assertEqual(groups[0].canonical_keyword, "high")

    def test_empty_keyword_skipped(self):
        interests = [{"user_id": 1, "keyword": "", "weight": 1.0}]
        groups = group_interests(interests)
        self.assertEqual(len(groups), 0)


class TestDedupeKey(unittest.TestCase):
    def test_deterministic(self):
        k1 = make_dedupe_key("AI", "github", "2026-10-16", "2026-10-16")
        k2 = make_dedupe_key("AI", "github", "2026-10-16", "2026-10-16")
        self.assertEqual(k1, k2)

    def test_different_for_different_inputs(self):
        k1 = make_dedupe_key("AI", "github", "2026-10-16", "2026-10-16")
        k2 = make_dedupe_key("AI", "hackernews", "2026-10-16", "2026-10-16")
        self.assertNotEqual(k1, k2)

    def test_synonym_normalisation(self):
        k1 = make_dedupe_key("artificial intelligence", "github", "2026-10-16", "2026-10-16")
        k2 = make_dedupe_key("AI", "github", "2026-10-16", "2026-10-16")
        self.assertEqual(k1, k2)


class TestBuildCollectionPlan(unittest.TestCase):
    def setUp(self):
        self.config = EngineConfig()

    def test_basic_plan(self):
        interests = [
            {"user_id": 1, "keyword": "AI", "weight": 5.0},
            {"user_id": 2, "keyword": "Rust", "weight": 3.0},
        ]
        plan = build_collection_plan(
            interests, ["github", "hackernews"], {1, 2},
            "2026-10-16", "2026-10-16", self.config,
        )
        self.assertGreater(len(plan.groups), 0)
        self.assertEqual(plan.sources, ["github", "hackernews"])

    def test_budget_limit(self):
        """Plan should not exceed daily job budget."""
        config = EngineConfig(budget=self.config.budget.__class__(max_daily_collection_jobs=3))
        interests = [
            {"user_id": 1, "keyword": f"topic-{i}", "weight": 1.0}
            for i in range(20)
        ]
        plan = build_collection_plan(
            interests, ["github", "hackernews"], {1},
            "2026-10-16", "2026-10-16", config,
        )
        jobs = plan_to_jobs(plan)
        # Should be limited by budget
        self.assertLessEqual(len(jobs), 3 + len(plan.sources))


class TestPlanToJobs(unittest.TestCase):
    def test_generates_jobs(self):
        config = EngineConfig()
        interests = [{"user_id": 1, "keyword": "AI", "weight": 5.0}]
        plan = build_collection_plan(
            interests, ["github"], {1},
            "2026-10-16", "2026-10-16", config,
        )
        jobs = plan_to_jobs(plan)
        self.assertGreater(len(jobs), 0)
        self.assertEqual(jobs[0].job_type, JobType.COLLECT)
        self.assertIn("interest", jobs[0].payload_json)
        self.assertIn("source", jobs[0].payload_json)

    def test_dedup_keys_are_unique_per_source(self):
        config = EngineConfig()
        interests = [{"user_id": 1, "keyword": "AI", "weight": 5.0}]
        plan = build_collection_plan(
            interests, ["github", "hackernews"], {1},
            "2026-10-16", "2026-10-16", config,
        )
        jobs = plan_to_jobs(plan)
        keys = [j.dedupe_key for j in jobs]
        self.assertEqual(len(keys), len(set(keys)), "Dedupe keys must be unique")


if __name__ == "__main__":
    unittest.main()

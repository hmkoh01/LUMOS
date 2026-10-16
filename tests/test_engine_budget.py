"""Offline tests for budget tracking and cost control.

Validates: usage recording, per-user limits, daily/monthly caps,
hard cap blocking, cached briefing not counting as usage.
"""

import os
import unittest

os.environ["LUMOS_TEST_MODE"] = "true"
os.environ["LUMOS_BLOCK_EXTERNAL_CALLS"] = "true"

from src.engine.budget.limits import FREE_BETA, get_plan, plan_to_budget_config
from src.engine.budget.tracker import BudgetTracker
from src.engine.config import BudgetConfig
from src.engine.models import UsageRecord


class TestBudgetTracker(unittest.TestCase):
    def setUp(self):
        self.config = BudgetConfig(
            max_chat_requests_per_day=3,
            max_daily_collection_jobs=5,
            max_daily_briefing_generations=10,
            max_daily_expensive_llm_calls=2,
            daily_budget_usd=1.0,
            monthly_budget_usd=10.0,
        )
        self.tracker = BudgetTracker(self.config)

    def test_record_and_check_chat(self):
        for i in range(3):
            self.tracker.record(UsageRecord(user_id=1, event_type="chat", tokens_used=100))
        self.assertFalse(self.tracker.check_user_chat_limit(1))

    def test_under_chat_limit(self):
        self.tracker.record(UsageRecord(user_id=1, event_type="chat", tokens_used=100))
        self.assertTrue(self.tracker.check_user_chat_limit(1))

    def test_daily_budget_exceeded(self):
        self.tracker.record(UsageRecord(event_type="llm_cheap", estimated_cost_usd=0.6))
        self.assertTrue(self.tracker.check_daily_budget())
        self.tracker.record(UsageRecord(event_type="llm_cheap", estimated_cost_usd=0.5))
        self.assertFalse(self.tracker.check_daily_budget())

    def test_monthly_budget(self):
        for i in range(11):
            self.tracker.record(UsageRecord(event_type="llm_cheap", estimated_cost_usd=1.0))
        self.assertFalse(self.tracker.check_monthly_budget())

    def test_collection_limit(self):
        for i in range(5):
            self.tracker.record(UsageRecord(event_type="collection"))
        self.assertFalse(self.tracker.check_daily_collection_limit())

    def test_expensive_llm_limit(self):
        self.tracker.record(UsageRecord(event_type="llm_expensive"))
        self.assertTrue(self.tracker.check_expensive_llm_limit())
        self.tracker.record(UsageRecord(event_type="llm_expensive"))
        self.assertFalse(self.tracker.check_expensive_llm_limit())

    def test_can_start_external_job(self):
        self.assertTrue(self.tracker.can_start_external_job())
        # Exhaust daily budget
        self.tracker.record(UsageRecord(event_type="llm_cheap", estimated_cost_usd=1.5))
        self.assertFalse(self.tracker.can_start_external_job())

    def test_usage_summary(self):
        self.tracker.record(UsageRecord(user_id=1, event_type="chat", tokens_used=500, estimated_cost_usd=0.01))
        summary = self.tracker.get_usage_summary(user_id=1)
        self.assertEqual(summary["daily_tokens"], 500)
        self.assertIn("limits", summary)


class TestCachedBriefingNotCounted(unittest.TestCase):
    """Displaying a cached briefing should NOT count as LLM usage."""

    def test_cache_display_is_free(self):
        config = BudgetConfig(cache_display_counts_as_usage=False)
        tracker = BudgetTracker(config)
        # No usage recorded for cache display
        self.assertTrue(tracker.check_daily_budget())
        # Only actual LLM calls count
        tracker.record(UsageRecord(event_type="cache_display"))
        # cache_display is not llm_cheap or llm_expensive, so budget check still passes
        self.assertTrue(tracker.check_daily_budget())


class TestPlanLimits(unittest.TestCase):
    def test_free_beta_plan(self):
        plan = get_plan("free_beta")
        self.assertEqual(plan.max_briefing_display, 5)
        self.assertEqual(plan.daily_budget_usd, 5.0)

    def test_plan_to_config(self):
        config = plan_to_budget_config(FREE_BETA)
        self.assertEqual(config.max_briefing_display_count, 5)
        self.assertEqual(config.max_daily_expensive_llm_calls, 10)

    def test_unknown_plan_defaults_to_free(self):
        plan = get_plan("unknown_plan")
        self.assertEqual(plan.name, "free_beta")


if __name__ == "__main__":
    unittest.main()

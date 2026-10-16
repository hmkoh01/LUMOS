"""Offline tests for external-call safety guard.

Validates: calls blocked by default, blocked by env var, blocked when
engine disabled, API keys ignored in test mode.
"""

import os
import unittest

os.environ["LUMOS_TEST_MODE"] = "true"

from src.engine.config import EngineConfig
from src.engine.safety import ExternalCallBlocked, check_external_call_allowed, is_test_environment


class TestSafetyGuard(unittest.TestCase):
    def test_blocked_by_default(self):
        config = EngineConfig()  # enabled=False, external_calls_allowed=False
        with self.assertRaises(ExternalCallBlocked):
            check_external_call_allowed(config, call_description="test call")

    def test_blocked_when_engine_disabled(self):
        config = EngineConfig(enabled=False, external_calls_allowed=True)
        with self.assertRaises(ExternalCallBlocked):
            check_external_call_allowed(config)

    def test_blocked_when_external_calls_off(self):
        config = EngineConfig(enabled=True, external_calls_allowed=False)
        with self.assertRaises(ExternalCallBlocked):
            check_external_call_allowed(config)

    def test_allowed_when_both_enabled(self):
        os.environ.pop("LUMOS_BLOCK_EXTERNAL_CALLS", None)
        config = EngineConfig(enabled=True, external_calls_allowed=True)
        # Should not raise
        check_external_call_allowed(config)

    def test_env_var_overrides(self):
        os.environ["LUMOS_BLOCK_EXTERNAL_CALLS"] = "true"
        config = EngineConfig(enabled=True, external_calls_allowed=True)
        with self.assertRaises(ExternalCallBlocked):
            check_external_call_allowed(config)
        os.environ.pop("LUMOS_BLOCK_EXTERNAL_CALLS", None)

    def test_api_key_present_still_blocked(self):
        """Even if a real API key is in the environment, calls are blocked in test mode."""
        os.environ["GEMINI_API_KEY"] = "real-key-should-not-matter"
        config = EngineConfig()  # defaults: disabled
        with self.assertRaises(ExternalCallBlocked):
            check_external_call_allowed(config)
        os.environ.pop("GEMINI_API_KEY", None)

    def test_is_test_environment(self):
        self.assertTrue(is_test_environment())


class TestSchedulerDisabledByDefault(unittest.TestCase):
    def test_scheduler_not_started(self):
        from src.engine.queue.scheduler import Scheduler
        config = EngineConfig()  # scheduler_enabled=False
        calls = []
        scheduler = Scheduler(config, lambda: calls.append(1))
        scheduler.start()  # should be a no-op
        self.assertFalse(scheduler.is_running())
        self.assertEqual(len(calls), 0)

    def test_scheduler_not_started_when_engine_disabled(self):
        from src.engine.config import CollectionConfig
        from src.engine.queue.scheduler import Scheduler
        config = EngineConfig(enabled=False, collection=CollectionConfig(scheduler_enabled=True))
        calls = []
        scheduler = Scheduler(config, lambda: calls.append(1))
        scheduler.start()
        self.assertFalse(scheduler.is_running())


if __name__ == "__main__":
    unittest.main()

"""Offline tests for LLM routing, caching, and validation.

Validates: rule-based Korean briefing, cache hit/miss, mock LLM calls,
validation, tiered routing.  No real API calls.
"""

import os
import unittest

os.environ["LUMOS_TEST_MODE"] = "true"
os.environ["LUMOS_BLOCK_EXTERNAL_CALLS"] = "true"

from src.engine.config import EngineConfig
from src.engine.llm.cache import BriefingCache
from src.engine.llm.providers import MockLLMProvider
from src.engine.llm.router import LLMRouter, _rule_based_briefing
from src.engine.llm.validator import ValidationResult, parse_llm_briefing_response, validate_briefing
from src.engine.models import KoreanBriefing, LLMTier, RawCandidate


class TestRuleBasedBriefing(unittest.TestCase):
    def test_korean_content_reused(self):
        c = RawCandidate(
            dedupe_key="kr-1",
            title="새로운 AI 프레임워크 출시",
            summary="한국어로 작성된 충분히 긴 요약입니다. 이 프레임워크는 혁신적인 기능을 제공합니다.",
        )
        result = _rule_based_briefing(c)
        self.assertIsNotNone(result)
        self.assertEqual(result.generated_by, LLMTier.RULE)
        self.assertEqual(result.display_title_ko, c.title)

    def test_english_content_not_rule_based(self):
        c = RawCandidate(
            dedupe_key="en-1",
            title="New AI Framework",
            summary="A new framework for building AI agents with Python.",
        )
        result = _rule_based_briefing(c)
        self.assertIsNone(result)

    def test_short_summary_not_rule_based(self):
        c = RawCandidate(
            dedupe_key="short-1",
            title="짧은 제목",
            summary="짧음",
        )
        result = _rule_based_briefing(c)
        self.assertIsNone(result)


class TestBriefingCache(unittest.TestCase):
    def setUp(self):
        self.cache = BriefingCache()

    def test_put_and_get(self):
        b = KoreanBriefing(dedupe_key="c-1", display_title_ko="제목", headline_summary_ko="요약")
        self.cache.put(b)
        fetched = self.cache.get("c-1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.display_title_ko, "제목")

    def test_miss(self):
        self.assertIsNone(self.cache.get("nonexistent"))

    def test_expired(self):
        b = KoreanBriefing(dedupe_key="exp-1", display_title_ko="제목", headline_summary_ko="요약", expires_at="2020-01-01T00:00:00+00:00")
        self.cache.put(b)
        self.assertIsNone(self.cache.get("exp-1"))

    def test_get_many(self):
        self.cache.put(KoreanBriefing(dedupe_key="m-1", display_title_ko="A", headline_summary_ko="B"))
        self.cache.put(KoreanBriefing(dedupe_key="m-2", display_title_ko="C", headline_summary_ko="D"))
        result = self.cache.get_many(["m-1", "m-2", "m-3"])
        self.assertEqual(len(result), 2)
        self.assertIn("m-1", result)
        self.assertNotIn("m-3", result)

    def test_upsert(self):
        self.cache.put(KoreanBriefing(dedupe_key="u-1", display_title_ko="Old", headline_summary_ko="X"))
        self.cache.put(KoreanBriefing(dedupe_key="u-1", display_title_ko="New", headline_summary_ko="Y"))
        self.assertEqual(self.cache.get("u-1").display_title_ko, "New")

    def test_no_duplicate_generation(self):
        """Same content should reuse cached briefing, not generate again."""
        self.cache.put(KoreanBriefing(dedupe_key="dup-check", display_title_ko="Cached", headline_summary_ko="Already done"))
        self.assertEqual(self.cache.count(), 1)
        # Putting same key again should not increase count
        self.cache.put(KoreanBriefing(dedupe_key="dup-check", display_title_ko="Updated", headline_summary_ko="Updated"))
        self.assertEqual(self.cache.count(), 1)


class TestValidation(unittest.TestCase):
    def test_valid_briefing(self):
        b = KoreanBriefing(
            display_title_ko="좋은 제목입니다",
            headline_summary_ko="이것은 충분히 긴 한국어 요약 텍스트입니다.",
            key_facts_ko=["사실 하나", "사실 둘"],
        )
        result = validate_briefing(b)
        self.assertTrue(result.valid)
        self.assertGreaterEqual(result.confidence, 0.8)

    def test_missing_title(self):
        b = KoreanBriefing(display_title_ko="", headline_summary_ko="Some summary here yes")
        result = validate_briefing(b)
        self.assertFalse(result.valid)

    def test_identical_title_summary(self):
        b = KoreanBriefing(display_title_ko="같은 텍스트입니다", headline_summary_ko="같은 텍스트입니다")
        result = validate_briefing(b)
        self.assertLess(result.confidence, 1.0)

    def test_parse_json_response(self):
        text = '{"display_title_ko": "제목", "headline_summary_ko": "요약입니다", "key_facts_ko": ["사실"]}'
        b = parse_llm_briefing_response(text)
        self.assertIsNotNone(b)
        self.assertEqual(b.display_title_ko, "제목")

    def test_parse_markdown_wrapped(self):
        text = '```json\n{"display_title_ko": "제목", "headline_summary_ko": "요약입니다 텍스트", "key_facts_ko": []}\n```'
        b = parse_llm_briefing_response(text)
        self.assertIsNotNone(b)

    def test_parse_invalid(self):
        self.assertIsNone(parse_llm_briefing_response("not json"))


class TestLLMRouter(unittest.TestCase):
    def setUp(self):
        self.config = EngineConfig()
        self.cache = BriefingCache()
        self.mock = MockLLMProvider()
        self.router = LLMRouter(self.config, self.cache, cheap_provider=self.mock)

    def test_rule_based_skips_llm(self):
        c = RawCandidate(
            dedupe_key="kr-route",
            title="한국어 제목이 있는 기사입니다",
            summary="이것은 한국어로 충분히 긴 요약 텍스트를 제공하는 항목입니다.",
        )
        result = self.router.generate_briefings([c])
        self.assertIn("kr-route", result)
        self.assertEqual(len(self.mock.calls), 0)

    def test_cache_hit_skips_llm(self):
        self.cache.put(KoreanBriefing(dedupe_key="cached-1", display_title_ko="제목", headline_summary_ko="요약입니다 텍스트"))
        c = RawCandidate(dedupe_key="cached-1", title="English Title", summary="English summary")
        result = self.router.generate_briefings([c])
        self.assertIn("cached-1", result)
        self.assertEqual(len(self.mock.calls), 0)

    def test_llm_called_for_english(self):
        c = RawCandidate(dedupe_key="en-route", title="English Only", summary="Only English content here")
        result = self.router.generate_briefings([c])
        self.assertEqual(len(self.mock.calls), 1)

    def test_batch_generation(self):
        candidates = [
            RawCandidate(dedupe_key=f"batch-{i}", title=f"Item {i}", summary=f"Summary {i}")
            for i in range(3)
        ]
        result = self.router.generate_briefings(candidates)
        # Mock produces single-item response, so some may be parsed
        self.assertGreater(len(result), 0)

    def test_cached_result_stored(self):
        c = RawCandidate(dedupe_key="store-check", title="English", summary="Content")
        self.router.generate_briefings([c])
        # Should be cached now
        cached = self.cache.get("store-check")
        self.assertIsNotNone(cached)

    def test_cost_tracking(self):
        c = RawCandidate(dedupe_key="cost-1", title="English", summary="Content")
        self.router.generate_briefings([c])
        self.assertEqual(self.router.cheap_calls, 1)
        self.assertGreater(self.router.tokens_used, 0)


if __name__ == "__main__":
    unittest.main()

"""Tiered LLM router: rule → cheap → expensive.

1. Try rule-based Korean briefing (no LLM cost).
2. Check shared cache (no LLM cost).
3. Generate with cheap model.
4. If validation fails, escalate to expensive model.

The router tracks costs via the budget system.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.engine.config import EngineConfig
from src.engine.llm.cache import BriefingCache
from src.engine.llm.providers import LLMProvider, LLMRequest, LLMResponse, MockLLMProvider
from src.engine.llm.validator import ValidationResult, parse_llm_briefing_response, validate_briefing
from src.engine.models import KoreanBriefing, LLMTier, RawCandidate
from src.engine.safety import ExternalCallBlocked, check_external_call_allowed

logger = logging.getLogger(__name__)


def _rule_based_briefing(candidate: RawCandidate) -> Optional[KoreanBriefing]:
    """Try to create a Korean briefing from metadata alone (no LLM).

    Works when the source already provides Korean text or when the
    content is simple enough to handle with templates.
    """
    title = candidate.title or ""
    summary = candidate.summary or ""

    # If the title/summary already contain Korean characters, reuse as-is
    def _has_korean(text: str) -> bool:
        return any("\uac00" <= c <= "\ud7a3" for c in text)

    if _has_korean(title) and _has_korean(summary) and len(summary) >= 20:
        return KoreanBriefing(
            dedupe_key=candidate.dedupe_key,
            display_title_ko=title,
            headline_summary_ko=summary,
            key_facts_ko=[],
            generated_by=LLMTier.RULE,
            confidence=0.9,
        )
    return None


def _build_prompt(candidates: List[RawCandidate]) -> str:
    """Build a batched prompt for Korean briefing generation."""
    items_text = []
    for i, c in enumerate(candidates):
        items_text.append(
            f"[{i+1}] Title: {c.title}\n"
            f"    Source: {c.source}\n"
            f"    Summary: {c.summary}\n"
            f"    URL: {c.url}"
        )
    items_block = "\n\n".join(items_text)
    return (
        "You are a Korean tech briefing writer. For each item below, generate:\n"
        "1. display_title_ko: A concise Korean title (max 60 chars)\n"
        "2. headline_summary_ko: A Korean summary (2-3 sentences)\n"
        "3. key_facts_ko: A list of 2-3 key facts in Korean\n\n"
        "Return a JSON array where each element has the keys above plus the item number.\n"
        "Use natural Korean. Do not transliterate — translate meaning.\n\n"
        f"Items:\n{items_block}\n\n"
        "Return ONLY valid JSON."
    )


class LLMRouter:
    """Routes briefing generation through rule → cache → cheap → expensive."""

    def __init__(
        self,
        config: EngineConfig,
        cache: BriefingCache,
        cheap_provider: Optional[LLMProvider] = None,
        expensive_provider: Optional[LLMProvider] = None,
    ):
        self.config = config
        self.cache = cache
        self.cheap = cheap_provider or MockLLMProvider()
        self.expensive = expensive_provider or MockLLMProvider()
        # Usage counters (per session, for budget tracking)
        self.cheap_calls = 0
        self.expensive_calls = 0
        self.tokens_used = 0

    def generate_briefings(
        self,
        candidates: List[RawCandidate],
    ) -> Dict[str, KoreanBriefing]:
        """Generate Korean briefings for a batch of candidates.

        Returns a dict keyed by dedupe_key.  Uses the tiered approach:
        rule → cache → cheap LLM → expensive LLM.
        """
        result: Dict[str, KoreanBriefing] = {}
        need_llm: List[RawCandidate] = []

        # Step 1: Try rule-based
        for c in candidates:
            rule = _rule_based_briefing(c)
            if rule is not None:
                self.cache.put(rule)
                result[c.dedupe_key] = rule
                continue
            # Step 2: Check cache
            cached = self.cache.get(c.dedupe_key)
            if cached is not None:
                result[c.dedupe_key] = cached
                continue
            need_llm.append(c)

        if not need_llm:
            return result

        # Step 3: Cheap LLM (batched)
        batch_size = self.config.llm.max_items_per_llm_call
        for i in range(0, len(need_llm), batch_size):
            batch = need_llm[i : i + batch_size]
            briefings = self._generate_with_tier(batch, LLMTier.CHEAP)
            need_expensive: List[RawCandidate] = []

            for c in batch:
                if c.dedupe_key in briefings:
                    b = briefings[c.dedupe_key]
                    validation = validate_briefing(b)
                    if validation.valid:
                        b.confidence = validation.confidence
                        b.generated_by = LLMTier.CHEAP
                        self.cache.put(b)
                        result[c.dedupe_key] = b
                    else:
                        need_expensive.append(c)
                else:
                    need_expensive.append(c)

            # Step 4: Expensive LLM for failures (if enabled)
            if need_expensive and self.config.llm.expensive_model_enabled:
                expensive_briefings = self._generate_with_tier(need_expensive, LLMTier.EXPENSIVE)
                for c in need_expensive:
                    if c.dedupe_key in expensive_briefings:
                        b = expensive_briefings[c.dedupe_key]
                        b.generated_by = LLMTier.EXPENSIVE
                        b.confidence = max(b.confidence, 0.7)
                        self.cache.put(b)
                        result[c.dedupe_key] = b

        return result

    def _generate_with_tier(
        self,
        candidates: List[RawCandidate],
        tier: str,
    ) -> Dict[str, KoreanBriefing]:
        """Call the LLM provider for a batch.  Returns briefings keyed by dedupe_key."""
        provider = self.cheap if tier == LLMTier.CHEAP else self.expensive
        max_tokens = (
            self.config.llm.cheap_model_max_tokens
            if tier == LLMTier.CHEAP
            else self.config.llm.expensive_model_max_tokens
        )

        prompt = _build_prompt(candidates)
        request = LLMRequest(prompt=prompt, max_tokens=max_tokens, tier=tier)

        try:
            response = provider.generate(request)
        except ExternalCallBlocked:
            logger.info("LLM call blocked by safety guard (tier=%s)", tier)
            return {}
        except Exception as exc:
            logger.exception("LLM generation failed (tier=%s): %s", tier, exc)
            return {}

        if tier == LLMTier.CHEAP:
            self.cheap_calls += 1
        else:
            self.expensive_calls += 1
        self.tokens_used += response.tokens_used

        return self._parse_batch_response(response.text, candidates)

    def _parse_batch_response(
        self,
        text: str,
        candidates: List[RawCandidate],
    ) -> Dict[str, KoreanBriefing]:
        """Parse a batched LLM response into individual briefings."""
        import json
        result: Dict[str, KoreanBriefing] = {}

        try:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines)
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            # Try single-item parse as fallback
            if len(candidates) == 1:
                b = parse_llm_briefing_response(text)
                if b:
                    b.dedupe_key = candidates[0].dedupe_key
                    result[candidates[0].dedupe_key] = b
            return result

        if isinstance(data, dict):
            data = [data]

        for i, item in enumerate(data):
            if i >= len(candidates):
                break
            c = candidates[i]
            b = KoreanBriefing(
                dedupe_key=c.dedupe_key,
                display_title_ko=item.get("display_title_ko", ""),
                headline_summary_ko=item.get("headline_summary_ko", ""),
                key_facts_ko=item.get("key_facts_ko", []),
            )
            result[c.dedupe_key] = b

        return result

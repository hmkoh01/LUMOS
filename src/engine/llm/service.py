"""Orchestrates validated shared content and per-user Engine v2 cards."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List

from src.engine.llm.briefing_adapter import content_to_engine_briefing, personalization_to_card_fields
from src.engine.llm.cache import BriefingCache
from src.engine.llm.providers import StructuredBriefingProvider
from src.engine.llm.structured_cache import StructuredBriefingCache
from src.engine.models import RawCandidate, ScoredCandidate
from src.engine.personalization.ranker import personalise_rankings
from src.engine.personalization.relevance import assess_candidate_relevance
from src.engine.personalization.interest_display import korean_display_interests


def _key(kind: str, parts: Dict[str, Any]) -> str:
    payload = json.dumps({"kind": kind, **parts}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EngineBriefingService:
    """A no-retry service layer; callers control queue scheduling separately."""

    def __init__(self, provider: StructuredBriefingProvider, shared_cache: BriefingCache,
                 structured_cache: StructuredBriefingCache) -> None:
        self.provider = provider
        self.shared_cache = shared_cache
        self.structured_cache = structured_cache

    def _record_usage(self, response: Dict[str, Any]) -> None:
        """Record aggregate provider usage only; prompts and profile data stay out of telemetry."""
        metadata = response.get("metadata") or {}
        # The shared Agent Platform client exposes usage directly in its
        # sanitized metadata.  Keep accepting a nested shape for offline
        # provider adapters, without depending on either form.
        usage = metadata.get("usage") or metadata
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        thinking_tokens = usage.get("thinking_tokens", usage.get("thought_tokens"))
        # The estimate is intentionally local/transparent.  It is not a
        # substitute for delayed Cloud billing and is only emitted when the
        # provider supplied actual token metadata.
        cost = metadata.get("estimated_cost_usd")
        if cost is None and all(isinstance(v, (int, float)) for v in (input_tokens, output_tokens, thinking_tokens)):
            model = str(metadata.get("model") or self.configured_model)
            prices = {"gemini-3.5-flash-lite": (0.30, 2.50)}.get(model)
            if prices:
                cost = (input_tokens * prices[0] + (output_tokens + thinking_tokens) * prices[1]) / 1_000_000
        values = {
            "llm_input_tokens": input_tokens,
            "llm_output_tokens": output_tokens,
            "llm_thinking_tokens": thinking_tokens,
            "llm_estimated_cost_usd": cost,
        }
        for metric, value in values.items():
            if isinstance(value, (int, float)) and value >= 0:
                self.structured_cache.record_metric(metric, float(value))

    @property
    def configured_model(self) -> str:
        return getattr(getattr(self.provider, "config", None), "llm", None).agent_platform_model if getattr(getattr(self.provider, "config", None), "llm", None) else ""

    def prepare_shared(self, candidates: Iterable[RawCandidate]) -> Dict[str, Any]:
        """Generate/cache one grounded Korean content briefing per source item."""
        result: Dict[str, Any] = {}
        for candidate in candidates:
            content_key = _key("content", {
                "dedupe_key": candidate.dedupe_key, "provider": self.provider.cache_version,
                # Sources sometimes amend a release at the same URL.  Reuse is
                # safe only while the source representation is unchanged.
                "source": {"title": candidate.title, "summary": candidate.summary,
                           "url": candidate.url, "published_at": candidate.published_at},
            })
            content = self.structured_cache.get_content(content_key)
            if content is None:
                self.structured_cache.record_metric("content_cache_miss")
                response = self.provider.generate_content(candidate)
                self.structured_cache.record_metric("llm_content_requests")
                self._record_usage(response)
                if response.get("status") not in ("success", "cached"):
                    self.structured_cache.record_metric("content_generation_failed")
                    continue
                content = response.get("content_briefing") or {}
                if not content.get("_validation", {}).get("valid"):
                    self.structured_cache.record_metric("content_validation_failed")
                    continue
                self.structured_cache.put_content(content_key, content)
            else:
                self.structured_cache.record_metric("content_cache_hit")
            briefing = content_to_engine_briefing(candidate.dedupe_key, content)
            if briefing is None:
                continue
            self.shared_cache.put(briefing)
            result[candidate.dedupe_key] = content
        return result

    def build_cards(self, scored: List[ScoredCandidate], *, role: str, interests: List[str],
                    ignored_keys: set[str], tracked_keys: set[str], display_limit: int = 5) -> List[Dict[str, Any]]:
        """Create user cards from shared content and profile-scoped cached reasons."""
        # Do not spend shared-content budget on a source that has no
        # source-grounded relation to this user's interests.
        relevant_scored = [
            item for item in scored
            if assess_candidate_relevance(item.candidate, interests).level != "insufficient"
        ]
        candidates = [item.candidate for item in relevant_scored]
        content_by_key = self.prepare_shared(candidates)
        eligible = [item for item in relevant_scored if item.candidate.dedupe_key in content_by_key]
        briefings = self.shared_cache.get_many([item.candidate.dedupe_key for item in eligible])
        card_fields: Dict[str, Dict[str, str]] = {}
        profile = {"role": role, "interests": sorted(interests)}
        display_interests = korean_display_interests(interests)

        for item in eligible:
            relevance = assess_candidate_relevance(item.candidate, interests)
            if relevance.level == "insufficient":
                continue
            personalization_key = _key("personalization", {
                "content": _key("content", {
                    "dedupe_key": item.candidate.dedupe_key, "provider": self.provider.cache_version,
                    "source": {"title": item.candidate.title, "summary": item.candidate.summary,
                               "url": item.candidate.url, "published_at": item.candidate.published_at},
                }), "profile": profile,
                "provider": self.provider.cache_version, "relevance": relevance.level,
            })
            personalization = self.structured_cache.get_personalization(personalization_key)
            if personalization is None:
                self.structured_cache.record_metric("personalization_cache_miss")
                response = self.provider.generate_personalization(
                    content_by_key[item.candidate.dedupe_key], role, display_interests,
                    {"level": relevance.level, "basis": relevance.basis},
                )
                self.structured_cache.record_metric("llm_personalization_requests")
                self._record_usage(response)
                if response.get("status") != "success":
                    self.structured_cache.record_metric("personalization_generation_failed")
                    continue
                personalization = response.get("personalization") or {}
                validated = personalization_to_card_fields(
                    personalization, relevance_level=relevance.level, relevance_basis=relevance.basis,
                )
                if validated is None:
                    self.structured_cache.record_metric("personalization_validation_failed")
                    continue
                self.structured_cache.put_personalization(personalization_key, personalization)
            else:
                self.structured_cache.record_metric("personalization_cache_hit")
            validated = personalization_to_card_fields(
                personalization, relevance_level=relevance.level, relevance_basis=relevance.basis,
            )
            if validated:
                card_fields[item.candidate.dedupe_key] = validated

        cards = personalise_rankings(
            eligible, interests, ignored_keys, tracked_keys, briefings,
            display_limit=display_limit, validated_card_fields=card_fields,
        )
        self.structured_cache.record_metric("cards_created", len(cards))
        if len(cards) < display_limit:
            self.structured_cache.record_metric("card_shortfall", display_limit - len(cards))
        return cards

"""Queue handler factory for the existing ``GENERATE_BRIEFING`` job type."""

from __future__ import annotations

from typing import Any, Dict, List

from src.engine.evaluation.scorer import evaluate_candidates, is_within_rolling_period
from src.engine.personalization.relevance import assess_candidate_relevance
from src.engine.llm.publisher import publish_engine_cards
from src.engine.llm.service import card_policy_versions
from src.engine.llm.metadata_cards import METADATA_ONLY_SOURCES, build_metadata_cards, metadata_publish_allowed
from src.engine.llm.card_quality import card_information_type_eligible
from src.engine.models import RawCandidate


def make_generate_briefing_job(*, dedupe_key: str, payload: Dict[str, Any], priority: int = 50):
    """Create a no-retry generation job; callers may explicitly opt in later."""
    from src.engine.models import Job, JobType
    return Job(job_type=JobType.GENERATE_BRIEFING, dedupe_key=dedupe_key,
               payload_json=payload, priority=priority, max_retries=0)


def _diverse_generation_candidates(scored, limit: int):
    """Reserve room for a materially competitive second source.

    Diversity is not a filler rule: a source's best candidate must retain at
    least 25% of the leading score and a source-grounded relevance assessment.
    """
    if not scored or limit < 2:
        return scored[:limit]
    top_score = scored[0].importance_score
    by_source = {}
    for item in scored:
        source = item.candidate.source or "unknown"
        if source not in by_source and item.importance_score >= max(0.1, top_score * 0.25):
            by_source[source] = item
    minimum = max(0.1, top_score * 0.25)
    chosen = []
    for item in sorted(by_source.values(), key=lambda entry: entry.importance_score, reverse=True):
        if len(chosen) >= limit:
            break
        chosen.append(item)
    chosen_keys = {item.candidate.dedupe_key for item in chosen}
    primary_source = scored[0].candidate.source or "unknown"
    chosen.extend(
        item for item in scored
        if item.candidate.dedupe_key not in chosen_keys
        and ((item.candidate.source or "unknown") == primary_source or item.importance_score >= minimum)
    )
    return chosen[:limit]


def make_generate_briefing_handler(service: Any, store: Any):
    """Return a Worker-compatible handler without starting workers/schedulers."""
    def handler(payload: Dict[str, Any], config: Any) -> Dict[str, Any]:
        user_id = int(payload["user_id"])
        period = payload.get("period", "daily")
        role = payload.get("role", "")
        interests = list(payload.get("interests", []))
        source_rows = store.get_enabled_source_configs(user_id=user_id)
        source_configs = {row["source_id"]: dict(row.get("config_json") or {}) for row in source_rows}
        allowed_sources = set(source_configs)
        candidates = [
            RawCandidate(**item) for item in payload.get("candidates", [])
            if not allowed_sources or item.get("source") in allowed_sources
        ]
        # Score metadata-only candidates with no generic interest expansion.
        # ``evaluate_candidates(..., interests)`` can invoke the legacy
        # interest matcher, which may translate an English interest. These
        # sources instead use the deterministic direct-match gate below.
        metadata_candidates = [candidate for candidate in candidates if candidate.source in METADATA_ONLY_SOURCES]
        llm_candidates = [candidate for candidate in candidates if candidate.source not in METADATA_ONLY_SOURCES]
        scored = evaluate_candidates(llm_candidates, period, interests, config)
        metadata_scored = evaluate_candidates(metadata_candidates, period, [], config)
        date_eligible_count = sum(
            1 for candidate in candidates
            if is_within_rolling_period(candidate.published_at, period) is not False
        )
        requested_display_limit = int(payload.get("display_limit", config.budget.max_briefing_display_count))
        display_limit = min(max(1, requested_display_limit), config.budget.max_briefing_display_count)
        generation_limit = min(
            max(display_limit, int(payload.get("generation_limit", display_limit + 3))),
            display_limit + config.personalization.max_reserve_candidates,
        )
        importance_eligible_count = len(scored) + len(metadata_scored)
        # Metadata-only sources have their own strict, source-aware matching
        # below. Do not let rejected metadata fall through to the LLM path.
        relevant_scored = [
            item for item in scored
            if assess_candidate_relevance(item.candidate, interests).level != "insufficient"
        ]
        # The generation cap is a hard external-call budget, not merely a
        # publishing limit.  Pass only the top relevant display candidates and
        # reserves into the LLM service so a large collection can never fan
        # out into unbounded Gemini content calls.
        ignored_keys = set(payload.get("ignored_keys", []))
        tracked_keys = set(payload.get("tracked_keys", []))
        # Metadata-only sources never reach EngineBriefingService: that class
        # calls the structured provider for content and personalisation.  A
        # blocked source is withheld rather than falling back to Gemini.
        publishable_metadata = [
            item for item in metadata_scored
            if metadata_publish_allowed(item.candidate.source, source_configs.get(item.candidate.source), user_id=user_id)
        ]
        metadata_cards, metadata_counts = build_metadata_cards(
            publishable_metadata, interests, ignored_keys, tracked_keys, display_limit=generation_limit,
        )
        # The generation cap is applied before calling the provider.  Apply
        # every deterministic information-type gate first; otherwise a
        # high-scoring but ineligible repository can consume one of the eight
        # slots and leave an eligible candidate below the cap ungenerated.
        # ``EngineBriefingService`` repeats this gate as defence in depth.
        llm_scored = [
            item for item in relevant_scored
            if item.candidate.source not in METADATA_ONLY_SOURCES
            and card_information_type_eligible(item.candidate, interests)[0]
        ]
        generation_candidates = _diverse_generation_candidates(
            llm_scored, max(0, generation_limit - len(metadata_cards)),
        )
        generation_diagnostics: Dict[str, int] = {}
        llm_cards = service.build_cards(
            generation_candidates, role=role, interests=interests,
            ignored_keys=ignored_keys, tracked_keys=tracked_keys,
            # Generate only the residual display set plus bounded reserves.
            display_limit=max(0, generation_limit - len(metadata_cards)),
            diagnostics=generation_diagnostics,
        ) if generation_candidates else []
        cards = sorted([*metadata_cards, *llm_cards], key=lambda card: card["scored"].importance_score, reverse=True)
        for index, card in enumerate(cards, 1):
            card["rank"] = index
        run_id = int(payload["pipeline_run_id"])
        provider_or_transport_failed = (
            generation_diagnostics.get("content_provider_or_transport_failed", 0)
            + generation_diagnostics.get("personalization_provider_or_transport_failed", 0)
        )
        if provider_or_transport_failed:
            generation_state = "generation_incomplete"
        elif cards:
            generation_state = "completed_with_valid_cards"
        elif (
            generation_diagnostics.get("content_validation_rejected", 0)
            or generation_diagnostics.get("personalization_validation_rejected", 0)
        ):
            generation_state = "validation_rejected_no_cards"
        else:
            generation_state = "completed_no_valid_cards"
        outcome = publish_engine_cards(
            store, cards, user_id=user_id, period=period, pipeline_run_id=run_id,
            display_limit=display_limit,
            preserve_existing_on_incomplete=bool(provider_or_transport_failed),
            expected_card_policy_versions=card_policy_versions(),
        )
        store.complete_pipeline_run(
            run_id,
            {**outcome, "period": period, "candidate_count": len(candidates),
             "date_eligible_count": date_eligible_count,
             "importance_eligible_count": importance_eligible_count,
             "relevant_candidate_count": len(relevant_scored) + len(metadata_scored),
             "generation_candidate_count": len(generation_candidates),
             "metadata_candidate_count": len(metadata_scored),
             "metadata_published_candidate_count": len(metadata_cards),
             "metadata_withheld_candidate_count": len(metadata_scored) - len(metadata_cards),
             "card_count": len(cards), "generation_state": generation_state,
             "generation_diagnostics": generation_diagnostics,
             "selected_sources": sorted(allowed_sources)},
            user_id=user_id,
        )
        return {**outcome, "period": period, "candidate_count": len(candidates),
                "date_eligible_count": date_eligible_count,
                "importance_eligible_count": importance_eligible_count,
                "relevant_candidate_count": len(relevant_scored) + len(metadata_scored),
                "generation_candidate_count": len(generation_candidates),
                "metadata_candidate_count": len(metadata_scored),
                "metadata_published_candidate_count": len(metadata_cards),
                "metadata_withheld_candidate_count": len(metadata_scored) - len(metadata_cards),
                "card_count": len(cards), "generation_state": generation_state,
                "generation_diagnostics": generation_diagnostics}
    return handler


def register_generate_briefing_handler(service: Any, store: Any) -> None:
    """Explicitly register the handler; importing this module has no side effect."""
    from src.engine.models import JobType
    from src.engine.queue.worker import register_handler
    register_handler(JobType.GENERATE_BRIEFING, make_generate_briefing_handler(service, store))

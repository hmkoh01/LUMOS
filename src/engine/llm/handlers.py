"""Queue handler factory for the existing ``GENERATE_BRIEFING`` job type."""

from __future__ import annotations

from typing import Any, Dict, List

from src.engine.evaluation.scorer import evaluate_candidates
from src.engine.llm.publisher import publish_engine_cards
from src.engine.models import RawCandidate


def make_generate_briefing_job(*, dedupe_key: str, payload: Dict[str, Any], priority: int = 50):
    """Create a no-retry generation job; callers may explicitly opt in later."""
    from src.engine.models import Job, JobType
    return Job(job_type=JobType.GENERATE_BRIEFING, dedupe_key=dedupe_key,
               payload_json=payload, priority=priority, max_retries=0)


def make_generate_briefing_handler(service: Any, store: Any):
    """Return a Worker-compatible handler without starting workers/schedulers."""
    def handler(payload: Dict[str, Any], config: Any) -> Dict[str, Any]:
        user_id = int(payload["user_id"])
        period = payload.get("period", "daily")
        role = payload.get("role", "")
        interests = list(payload.get("interests", []))
        allowed_sources = {row["source_id"] for row in store.get_enabled_source_configs(user_id=user_id)}
        candidates = [
            RawCandidate(**item) for item in payload.get("candidates", [])
            if not allowed_sources or item.get("source") in allowed_sources
        ]
        scored = evaluate_candidates(candidates, period, interests, config)
        cards = service.build_cards(
            scored, role=role, interests=interests,
            ignored_keys=set(payload.get("ignored_keys", [])),
            tracked_keys=set(payload.get("tracked_keys", [])),
            # Generate all already-ranked candidates once; publisher splits
            # display/reserve cards without an additional LLM call.
            display_limit=100,
        )
        run_id = int(payload["pipeline_run_id"])
        outcome = publish_engine_cards(
            store, cards, user_id=user_id, period=period, pipeline_run_id=run_id,
            display_limit=int(payload.get("display_limit", config.budget.max_briefing_display_count)),
        )
        return {**outcome, "period": period, "card_count": len(cards)}
    return handler


def register_generate_briefing_handler(service: Any, store: Any) -> None:
    """Explicitly register the handler; importing this module has no side effect."""
    from src.engine.models import JobType
    from src.engine.queue.worker import register_handler
    register_handler(JobType.GENERATE_BRIEFING, make_generate_briefing_handler(service, store))

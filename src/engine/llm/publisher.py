"""Persist already-validated Engine cards through the existing signals tables."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, List

from src.engine.llm.briefing_adapter import engine_card_to_display_payload


def _signal_from_card(card: Dict[str, Any], period: str) -> Dict[str, Any]:
    payload = engine_card_to_display_payload(card)
    if payload is None:
        raise ValueError("Engine card is missing validated briefing data")
    candidate = card["candidate"]
    metadata = {
        "briefing_version": 9,
        "briefing_provider": "engine-v2-structured",
        "display_title_ko": payload["display_title_ko"],
        "headline_summary_ko": payload["headline_summary_ko"],
        "recommendation_reason_ko": payload["recommendation_reason_ko"],
        "why_it_matters_ko": payload["why_it_matters_ko"],
        "recommended_action_ko": payload["recommended_action_ko"],
        "relevance_level": payload["relevance_level"],
        "relevance_basis": payload["relevance_basis"],
        "engine_period": period,
    }
    return {
        "dedupe_key": f"engine-v2:{candidate.dedupe_key}",
        "signal_date": date.today().isoformat(),
        "title": candidate.title,
        "summary": candidate.summary,
        "why_it_matters": payload["why_it_matters_ko"],
        "recommended_action": payload["recommended_action_ko"],
        "category": "engine-v2",
        "source_name": candidate.source,
        "source_url": candidate.url,
        "source_items_json": [{
            "source": candidate.source, "title": candidate.title, "summary": candidate.summary,
            "url": candidate.url, "published_at": candidate.published_at,
            "dedupe_key": candidate.dedupe_key,
        }],
        "metadata_json": metadata,
        "confidence": card["scored"].importance_score,
        "rank": card["rank"], "status": "active",
    }


def publish_engine_cards(store: Any, cards: Iterable[Dict[str, Any]], *, user_id: int,
                         period: str, pipeline_run_id: int, display_limit: int) -> Dict[str, Any]:
    """Store display and reserve cards idempotently for one user/run.

    Existing rows are never overwritten: saved state and recommendation
    preferences therefore survive a repeat queue delivery.
    """
    prepared = [_signal_from_card(card, period) for card in cards]
    primary = prepared[:display_limit]
    reserves = prepared[display_limit:]
    created = 0
    with store.connect() as conn:
        existing = {
            row["dedupe_key"] for row in conn.execute(
                "SELECT dedupe_key FROM signals WHERE user_id = ? AND status != 'archived'", (user_id,)
            )
        }
    for signal in primary:
        if signal["dedupe_key"] in existing:
            continue
        store.create_signal(signal, pipeline_run_id=pipeline_run_id, user_id=user_id)
        existing.add(signal["dedupe_key"])
        created += 1
    # Reserves use the existing table; the API backfill path recognizes the
    # prepared Engine signal and never regenerates or calls an LLM on GET.
    with store.connect() as conn:
        existing_reserves = conn.execute(
            "SELECT COUNT(*) FROM signal_reserves WHERE pipeline_run_id = ?", (pipeline_run_id,)
        ).fetchone()[0]
    if reserves and not existing_reserves:
        store.save_signal_reserves(
            pipeline_run_id, [{"_engine_signal": signal} for signal in reserves], len(primary), user_id=user_id,
        )
    return {"created": created, "skipped_existing": len(primary) - created, "reserve_count": len(reserves)}

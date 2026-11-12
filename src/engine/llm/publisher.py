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
    # Older rows did not record which card policy created them.  Preserve the
    # field only for new Engine cards so historical rows remain readable while
    # future investigations can reliably distinguish v7/v8 output.
    if card.get("card_policy_versions"):
        metadata["card_policy_versions"] = dict(card["card_policy_versions"])
    return {
        # A source may legitimately rank in more than one independently
        # evaluated briefing period.  Include the period so a daily card does
        # not suppress its weekly/monthly counterpart.
        "dedupe_key": f"engine-v2:{period}:{candidate.dedupe_key}",
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
                         period: str, pipeline_run_id: int, display_limit: int,
                         preserve_existing_on_incomplete: bool = False,
                         expected_card_policy_versions: Dict[str, str] | None = None) -> Dict[str, Any]:
    """Store display and reserve cards idempotently for one user/run.

    Existing rows are never overwritten: saved state and recommendation
    preferences therefore survive a repeat queue delivery.
    """
    prepared = [_signal_from_card(card, period) for card in cards]
    primary = prepared[:display_limit]
    reserves = prepared[display_limit:]
    reconciliation = store.reconcile_engine_period_cards(
        primary, user_id=user_id, period=period, pipeline_run_id=pipeline_run_id,
        preserve_existing_on_incomplete=preserve_existing_on_incomplete,
        expected_card_policy_versions=expected_card_policy_versions,
        display_limit=display_limit,
    )
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
    return {**reconciliation, "skipped_existing": reconciliation["retained"], "reserve_count": len(reserves)}


def publish_metadata_pilot_cards(store: Any, cards: Iterable[Dict[str, Any]], *, user_id: int,
                                 pipeline_run_id: int) -> Dict[str, int]:
    """Append a bounded metadata Pilot without reconciling a user's feed.

    A source-scoped Pilot must never archive unrelated Engine cards merely
    because its narrow company query returned zero or one disclosure. Existing
    source/period reconciliation remains the normal production path.
    """
    prepared = [_signal_from_card(card, "daily") for card in cards]
    created = retained = 0
    with store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for signal in prepared:
            existing = conn.execute(
                "SELECT id FROM signals WHERE user_id = ? AND dedupe_key = ? LIMIT 1",
                (user_id, signal["dedupe_key"]),
            ).fetchone()
            if existing:
                retained += 1
                continue
            store._insert_signal(conn, signal, pipeline_run_id, user_id)
            created += 1
        conn.commit()
    return {"created": created, "retained": retained, "archived": 0, "reserve_count": 0}

"""Explicit bridge from a validated signals briefing to Engine v2 card data.

The bridge is deliberately pure: importing an experiment result never writes
to an operational database or enables a provider.  A caller may cache the
returned shared briefing only after its own Engine v2 safety gate permits it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.engine.models import KoreanBriefing, LLMTier


def content_to_engine_briefing(
    dedupe_key: str,
    content: Dict[str, Any],
) -> Optional[KoreanBriefing]:
    """Convert only a content result that passed the fact validator."""
    validation = content.get("_validation", {})
    if not validation.get("valid"):
        return None
    title = content.get("display_title_ko", "").strip()
    summary = content.get("display_summary_ko", "").strip()
    if not title or not summary:
        return None
    facts = content.get("key_facts", [])
    if not facts:
        facts = [fact.get("claim", "") for fact in content.get("grounded_facts", [])]
    facts = [fact for fact in facts if isinstance(fact, str) and fact.strip()]
    return KoreanBriefing(
        dedupe_key=dedupe_key,
        display_title_ko=title,
        headline_summary_ko=summary,
        key_facts_ko=facts,
        generated_by=LLMTier.CHEAP,
        confidence=0.9,
    )


def personalization_to_card_fields(
    personalization: Dict[str, Any],
    *,
    relevance_level: str,
    relevance_basis: str,
) -> Optional[Dict[str, str]]:
    """Expose only a validated, source-anchored per-user card explanation."""
    validation = personalization.get("_validation", {})
    if not validation.get("valid") or relevance_level == "insufficient":
        return None
    reason = personalization.get("recommendation_reason_ko", "").strip()
    if not reason:
        return None
    return {
        "recommendation_reason_ko": reason,
        "why_it_matters_ko": personalization.get("why_it_matters_ko", "").strip(),
        "recommended_action_ko": personalization.get("recommended_action_ko", "").strip(),
        "relevance_level": relevance_level,
        "relevance_basis": relevance_basis,
    }


def experiment_item_to_engine_card(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Rehydrate a safe card from a Git-ignored experiment result.

    This is intentionally an explicit import boundary.  It makes historic
    successful experiments reusable for offline integration tests while never
    reading an operational DB or enabling an LLM provider.
    """
    if item.get("content_status") != "success":
        return None
    validation = item.get("content_validation", {})
    if not validation.get("valid"):
        return None
    facts = [
        detail.get("claim", "")
        for detail in validation.get("checks", {}).get("fact_grounding", {}).get("details", [])
        if detail.get("quote_found") and detail.get("meaning_supported")
    ]
    content = {
        "display_title_ko": item.get("display_title_ko", ""),
        "display_summary_ko": item.get("display_summary_ko", ""),
        "key_facts": facts,
        "_validation": validation,
    }
    briefing = content_to_engine_briefing(item.get("id", ""), content)
    if briefing is None:
        return None
    card = {"briefing": briefing, "card_fields": None}
    if item.get("personalize_status") == "success":
        personalization = {
            key: item.get(key, "")
            for key in (
                "source_facts_ko", "user_relevance_ko", "recommendation_reason_ko",
                "why_it_matters_ko", "recommended_action_ko", "relevance_confidence",
            )
        }
        personalization["_validation"] = item.get("personalization_validation", {})
        # Re-run the current offline validator.  Historic experimental output
        # may have passed an older, less-specific policy.
        from src.signals.llm_briefing_validator import validate_personalization
        validation_content = {
            "display_title_ko": briefing.display_title_ko,
            "key_entities": [item.get("source_title", "")],
            "grounded_facts": [
                {"source_quote": detail.get("source_quote", "")}
                for detail in validation.get("checks", {}).get("fact_grounding", {}).get("details", [])
            ],
        }
        personalization["_validation"] = validate_personalization(personalization, validation_content)
        card["card_fields"] = personalization_to_card_fields(
            personalization,
            relevance_level=item.get("relevance_level", ""),
            relevance_basis=item.get("relevance_basis", ""),
        )
    return card


def engine_card_to_display_payload(card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map an Engine card to the existing read-only signal-card field names."""
    briefing = card.get("briefing")
    candidate = card.get("candidate")
    if briefing is None or candidate is None:
        return None
    return {
        "dedupe_key": card.get("dedupe_key", ""),
        "rank": card.get("rank"),
        "title": candidate.title,
        "summary": candidate.summary,
        "url": candidate.url,
        "source": candidate.source,
        "display_title_ko": briefing.display_title_ko,
        "headline_summary_ko": briefing.headline_summary_ko,
        "recommendation_reason_ko": card.get("recommendation_reason_ko", ""),
        "why_it_matters_ko": card.get("why_it_matters_ko", ""),
        "recommended_action_ko": card.get("recommended_action_ko", ""),
        "relevance_level": card.get("relevance_level", ""),
        "relevance_basis": card.get("relevance_basis", ""),
    }

"""Deterministic, metadata-only cards for approved domestic sources.

This module never imports a Gemini client, translation helper, or collector.
Preview creation is in-memory; publication is separately permission-gated.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from src.engine.models import KoreanBriefing, LLMTier, ScoredCandidate
from src.sources.source_registry import is_limited_opendart_pilot, source_usage_permission


METADATA_ONLY_SOURCES = frozenset({"tourapi", "opendart", "public_institution_jobs"})
_REGION_TERMS = (
    "seoul", "busan", "daejeon", "daegu", "ulsan", "incheon", "gwangju", "sejong",
    "\uc11c\uc6b8", "\ubd80\uc0b0", "\ub300\uc804", "\ub300\uad6c", "\uc6b8\uc0b0", "\uc778\ucc9c", "\uad11\uc8fc", "\uc138\uc885",
)
_EVENT_TERMS = (
    "festival", "\ucd95\uc81c", "exhibition", "\uc804\uc2dc", "performance", "\uacf5\uc5f0",
    "culture", "\ubb38\ud654", "event", "\ud589\uc0ac",
)
_REGION_ALIAS_GROUPS = (
    ("seoul", "\uc11c\uc6b8"), ("busan", "\ubd80\uc0b0"), ("daejeon", "\ub300\uc804"),
    ("daegu", "\ub300\uad6c"), ("ulsan", "\uc6b8\uc0b0"), ("incheon", "\uc778\ucc9c"),
    ("gwangju", "\uad11\uc8fc"), ("sejong", "\uc138\uc885"),
)
_EVENT_ALIAS_GROUPS = (
    ("festival", "\ucd95\uc81c"), ("exhibition", "\uc804\uc2dc"),
    ("performance", "\uacf5\uc5f0"), ("culture", "\ubb38\ud654"), ("event", "\ud589\uc0ac"),
)


def metadata_publish_allowed(source: str, source_config: Mapping[str, Any] | None = None, *, user_id: int | None = None) -> bool:
    """Require metadata-display and production-access approval to publish."""
    if source not in METADATA_ONLY_SOURCES:
        return False
    config = dict(source_config or {})
    # OpenDART's explicit one-user Pilot is a metadata-only exception. Its
    # process-level allowlist is enforced by EngineOperations, while this
    # branch keeps the Registry-wide production scope in permission review.
    if source == "opendart" and is_limited_opendart_pilot(config):
        return user_id is not None and int(config.get("pilot_user_id") or 0) == int(user_id)
    metadata = source_usage_permission(source, "metadata_display")["state"]
    production = source_usage_permission(source, "production_api_access")["state"]
    return bool(
        config.get("metadata_card_publish_approved")
        and metadata.startswith("allowed")
        and production in {"allowed", "allowed_with_attribution", "allowed_with_source_link"}
    )


def build_metadata_cards(
    scored: Iterable[ScoredCandidate],
    interests: Iterable[str],
    ignored_keys: set[str],
    tracked_keys: set[str],
    *,
    display_limit: int,
    verified_company_aliases: Mapping[str, str] | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Create deterministic cards in memory; an LLM fallback is impossible."""
    cards: List[Dict[str, Any]] = []
    counts = {"seen": 0, "eligible": 0, "withheld": 0}
    seen_keys: set[str] = set()
    for entry in scored:
        candidate = entry.candidate
        if candidate.source not in METADATA_ONLY_SOURCES:
            continue
        counts["seen"] += 1
        if candidate.dedupe_key in seen_keys or candidate.dedupe_key in ignored_keys:
            counts["withheld"] += 1
            continue
        seen_keys.add(candidate.dedupe_key)
        card = _build_card(entry, list(interests), verified_company_aliases or {})
        if card is None:
            counts["withheld"] += 1
            continue
        if candidate.dedupe_key in tracked_keys:
            entry.importance_score *= 1.2
        cards.append(card)
        counts["eligible"] += 1
    cards.sort(key=lambda card: card["scored"].importance_score, reverse=True)
    for index, card in enumerate(cards[:display_limit], 1):
        card["rank"] = index
    return cards[:display_limit], counts


def _build_card(entry: ScoredCandidate, interests: List[str], verified_company_aliases: Mapping[str, str]) -> Dict[str, Any] | None:
    if entry.candidate.source == "tourapi":
        return _tour_card(entry, interests)
    if entry.candidate.source == "opendart":
        return _dart_card(entry, interests, verified_company_aliases)
    if entry.candidate.source == "public_institution_jobs":
        return _public_institution_job_card(entry, interests)
    return None


def _tour_card(entry: ScoredCandidate, interests: List[str]) -> Dict[str, Any] | None:
    candidate, data = entry.candidate, entry.candidate.metrics or {}
    if not candidate.url or not candidate.title:
        return None
    if data.get("content_kind") != "culture_event" or data.get("event_status") not in {"upcoming", "ongoing"}:
        return None
    start, end = data.get("event_start_at"), data.get("event_end_at")
    region, venue = str(data.get("region") or ""), str(data.get("venue") or "")
    if not start or not end or not region or not venue:
        return None
    matched = _tour_interest(interests, candidate.title, region, str(data.get("genre") or ""))
    if not matched:
        return None
    title = f"{candidate.title} - {venue}"
    summary = f"\ud589\uc0ac \uc77c\uc815: {start}~{end} | \uc7a5\uc18c: {venue}"
    reason = f"'{matched}' \uad00\uc2ec\uc0ac\uc640 \ud589\uc0ac \uc9c0\uc5ed \ub610\ub294 \uc720\ud615\uc774 \uc9c1\uc811 \uc77c\uce58\ud569\ub2c8\ub2e4."
    return _card(entry, title, summary, reason, [f"\ud589\uc0ac \uc77c\uc815: {start}~{end}"])


def _dart_card(entry: ScoredCandidate, interests: List[str], verified_company_aliases: Mapping[str, str]) -> Dict[str, Any] | None:
    candidate, data = entry.candidate, entry.candidate.metrics or {}
    company = str(candidate.author or "").strip()
    receipt = str(data.get("receipt_at") or "").strip()
    if not candidate.url or not candidate.title or not company or not receipt:
        return None
    matched = _company_interest(interests, company, verified_company_aliases)
    if not matched:
        return None
    title = f"{company} \uacf5\uc2dc: {candidate.title}"
    summary = f"\uacf5\uc2dc \uc811\uc218\uc77c: {receipt}"
    reason = f"\uba85\uc2dc\ud55c \uad00\uc2ec \uae30\uc5c5 '{matched}'\uc758 \uacf5\uc2dc\uc785\ub2c8\ub2e4."
    return _card(entry, title, summary, reason, [f"\uacf5\uc2dc \uc811\uc218\uc77c: {receipt}"])


def _public_institution_job_card(entry: ScoredCandidate, interests: List[str]) -> Dict[str, Any] | None:
    """Render only fully evidenced internship-list metadata.

    The list response's date is an announcement-date field.  It is useful as
    a dated notice, but is never promoted to an application deadline or an
    "open now" claim.  This source therefore cannot fall through to LLM
    generation when its permission gate is closed.
    """
    candidate, data = entry.candidate, entry.candidate.metrics or {}
    employer = str(candidate.author or "").strip()
    job_type = str(data.get("job_type") or "").strip()
    job_classification = str(data.get("job_classification") or "").strip()
    region = str(data.get("region") or "").strip()
    announcement_date = str(data.get("announcement_start_at") or candidate.published_at or "").strip()
    if not all((candidate.url, candidate.title, employer, region, announcement_date, job_type or job_classification)):
        return None
    matched = _internship_interest(interests, candidate.title, job_type, job_classification, str(data.get("recruitment_type") or ""))
    if not matched:
        return None
    job_label = " / ".join(part for part in (job_type, job_classification) if part)
    title = f"{employer} \uc778\ud134 \ucc44\uc6a9: {candidate.title}"
    summary = f"\uacf5\uace0 \uae30\uc900\uc77c: {announcement_date} | \uc9c1\ubb34: {job_label} | \uadfc\ubb34 \uc9c0\uc5ed: {region}"
    reason = f"'{matched}' \uad00\uc2ec\uc0ac\uc640 \uacf5\uace0\uc758 \uc778\ud134 \uc9c1\uc811 \uadfc\uac70\uac00 \uc77c\uce58\ud569\ub2c8\ub2e4."
    return _card(entry, title, summary, reason, [
        f"\uacf5\uace0 \uae30\uc900\uc77c: {announcement_date}",
        f"\uc9c1\ubb34: {job_label}",
        f"\uadfc\ubb34 \uc9c0\uc5ed: {region}",
        "\uc2e4\uc81c \uc811\uc218 \ub9c8\uac10\uc77c\uacfc \uc9c0\uc6d0 \uac00\ub2a5 \uc5ec\ubd80\ub294 \uacf5\uc2dd \uacf5\uace0\uc5d0\uc11c \ud655\uc778\ud558\uc138\uc694.",
    ])


def _card(entry: ScoredCandidate, title: str, summary: str, reason: str, facts: List[str]) -> Dict[str, Any]:
    candidate = entry.candidate
    return {
        "rank": 0,
        "dedupe_key": candidate.dedupe_key,
        "candidate": candidate,
        "scored": entry,
        "briefing": KoreanBriefing(
            dedupe_key=candidate.dedupe_key,
            display_title_ko=title,
            headline_summary_ko=summary,
            key_facts_ko=facts,
            generated_by=LLMTier.RULE,
            confidence=1.0,
        ),
        "recommendation_reason_ko": reason,
        "why_it_matters_ko": "\uacf5\uc2dd \uba54\ud0c0\ub370\uc774\ud130\uc758 \uc77c\uc815 \ub610\ub294 \uc811\uc218\uc77c\uc744 \ud655\uc778\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.",
        "recommended_action_ko": "\uacf5\uc2dd \uc6d0\ubb38 \ub9c1\ud06c\uc5d0\uc11c \uc138\ubd80 \ub0b4\uc6a9\uc744 \ud655\uc778\ud558\uc138\uc694.",
        "relevance_level": "direct",
        "relevance_basis": "metadata_direct_match",
    }


def _tour_interest(interests: Iterable[str], title: str, region: str, genre: str) -> str:
    haystack = _normalise(f"{title} {region} {genre}")
    for interest in interests:
        text = _normalise(interest)
        if not text:
            continue
        region_terms = [term for term in _REGION_TERMS if _normalise(term) in text]
        event_terms = [term for term in _EVENT_TERMS if _normalise(term) in text]
        region_ok = not region_terms or _alias_matches(text, _normalise(region), _REGION_ALIAS_GROUPS)
        event_ok = not event_terms or _alias_matches(text, haystack, _EVENT_ALIAS_GROUPS)
        if region_ok and event_ok and (region_terms or event_terms):
            return str(interest)
    return ""


def _company_interest(interests: Iterable[str], company: str, verified_company_aliases: Mapping[str, str] | None = None) -> str:
    company_key = _normalise(company)
    for interest in interests:
        interest_key = _normalise(interest)
        # Direct literal containment accepts a user-entered company name, but
        # rejects general economy/industry interests.
        if len(interest_key) >= 3 and (interest_key in company_key or company_key in interest_key):
            return str(interest)
        # An operator-provided alias is valid only when it names the exact
        # canonical corporation returned by the official stock-code cache.
        if _normalise((verified_company_aliases or {}).get(str(interest), "")) == company_key:
            return str(interest)
    return ""


def _internship_interest(interests: Iterable[str], *fields: str) -> str:
    evidence = _normalise(" ".join(fields))
    has_intern_evidence = "\uc778\ud134" in evidence or "intern" in evidence
    if not has_intern_evidence:
        return ""
    for interest in interests:
        interest_text = _normalise(interest)
        if "\uc778\ud134" in interest_text or "intern" in interest_text:
            return str(interest)
    return ""


def _normalise(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _alias_matches(interest: str, candidate: str, groups: Iterable[Tuple[str, ...]]) -> bool:
    """Match only known label aliases; this is not translation or inference."""
    for group in groups:
        if any(_normalise(alias) in interest for alias in group) and any(_normalise(alias) in candidate for alias in group):
            return True
    return False

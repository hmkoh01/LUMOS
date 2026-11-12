"""Explain which approved live collectors can serve an interest."""

from __future__ import annotations

from typing import Dict, Iterable, Optional

from src.sources.router import ROUTING_RULES, SourceRouter
from src.sources.source_registry import source_availability


_APPROVAL_REQUIRED_CATEGORIES = {
    "STARTUP_PROGRAM",
    "ECONOMY_FINANCE",
    "YOUTH_POLICY",
    "CULTURE_TRAVEL_EVENT",
    "INDUSTRY_POLICY",
    "CAREER",
}

# When an interest explicitly names one of these domains, its generic overlap
# (for example, "startup" also matching product discovery) must not leak into
# a technology/community-only pilot.
_SPECIALIZED_CATEGORIES = _APPROVAL_REQUIRED_CATEGORIES | {"RESEARCH"}


def _profile_for_interest(profile: Optional[Dict[str, object]], keyword: str) -> Dict[str, object]:
    """Keep source support scoped to the interest currently being planned.

    ``SourceRouter.classify_interests`` intentionally considers a whole
    profile when building a user-facing overview.  Reusing that broad context
    here made an approved developer-technology source disappear when the
    same user also selected an approval-gated type such as AI industry news:
    the latter category won the specialised-category gate for *every*
    interest.  Collection is planned once per interest, so only that
    interest's explicit type choice may constrain this decision.
    """
    raw = dict((profile or {}).get("raw_onboarding_json") or (profile or {}).get("raw_onboarding") or {})
    preferences = raw.get("interest_type_preferences")
    normalized = " ".join(str(keyword or "").casefold().split())
    if isinstance(preferences, dict):
        raw["interest_type_preferences"] = {
            str(name): value
            for name, value in preferences.items()
            if " ".join(str(name or "").casefold().split()) == normalized
        }
    else:
        raw["interest_type_preferences"] = {}
    # Role, goals, legacy display labels, and types selected for another
    # interest are useful profile context but must not silently route this
    # one interest to an unrelated or approval-gated source.
    return {
        "role": "",
        "role_detail": "",
        "goals_json": [],
        "interest_types_json": [],
        "raw_onboarding_json": raw,
    }


def collection_support(
    keyword: str,
    approved_sources: Iterable[str],
    source_configs: Optional[Iterable[Dict[str, object]]] = None,
    profile: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Return only approved sources that are relevant to an interest.

    Scheduled and onboarding collection both call this function. Keeping the
    category boundary here prevents a technology-only pilot allowlist from
    silently sending finance, policy, career, or travel interests to GitHub or
    Hacker News.
    """
    categories = SourceRouter().classify_interests(
        _profile_for_interest(profile, keyword), [{"keyword": keyword, "status": "active"}]
    )
    routed_categories = set(categories)
    specific_categories = routed_categories & _SPECIALIZED_CATEGORIES
    if specific_categories:
        routed_categories = specific_categories
    relevant_sources = {
        source
        for category in routed_categories
        for source in ROUTING_RULES.get(category, [])
    }
    approved_sources = tuple(approved_sources)
    configs = {str(row.get("source_id")): dict(row.get("config_json") or {}) for row in source_configs or []}
    # A named-company disclosure is not a general economy interest. When a
    # user has an exact, operator-verified stock-code identity, route only
    # that one interest to OpenDART even if generic keyword classification is
    # intentionally conservative.
    opendart_config = configs.get("opendart", {})
    normalized_keyword = " ".join(str(keyword or "").casefold().split())
    verified_company_interest = any(
        normalized_keyword == " ".join(str(entry.get("interest") or "").casefold().split())
        and str(entry.get("stock_code") or "").strip().isdigit()
        for entry in (opendart_config.get("verified_company_identities") or [])
        if isinstance(entry, dict)
    )
    if verified_company_interest:
        relevant_sources.add("opendart")
    candidate_states = {
        source: source_availability(source, configs.get(source))
        for source in sorted(relevant_sources)
    }
    for source, state in candidate_states.items():
        state["runtime_allowed"] = source in approved_sources
    sources = [
        source for source in approved_sources
        if source in relevant_sources and candidate_states[source]["available"]
    ]
    if sources:
        return {
            "status": "supported",
            "sources": sources,
            "categories": sorted(categories), "source_states": candidate_states,
            "message": "Approved sources are available for this interest.",
        }

    states = {entry["state"] for entry in candidate_states.values()}
    needs_approval = bool(routed_categories & _APPROVAL_REQUIRED_CATEGORIES) or "permission_review" in states
    status = "awaiting_approved_source" if needs_approval else (
        "awaiting_runtime_approval" if any(
                state["available"] and not state["runtime_allowed"]
                for state in candidate_states.values()
            ) else ("awaiting_configuration" if "configuration_required" in states else "no_approved_source")
    )
    return {
        "status": status,
        "sources": [],
        "categories": sorted(categories), "source_states": candidate_states,
        "message": "No approved live source is configured for this interest yet.",
    }


def first_briefing_candidate_state(
    support: Dict[str, object], candidate_count: Optional[int] = None, *, collection_observed: bool = False,
) -> str:
    """Separate no operational source from an empty evaluated source pool."""
    if support.get("status") != "supported":
        return "no_operational_source"
    if candidate_count is None and not collection_observed:
        return "collection_pending"
    return "candidates_available" if int(candidate_count or 0) > 0 else "no_matching_candidates"

"""Per-user ranking and recommendation reason generation.

Takes scored candidates (from the shared evaluation step) and
personalises them based on the user's interests, feedback history,
and preference signals.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from src.engine.models import KoreanBriefing, RawCandidate, RecommendationReason, ScoredCandidate
from src.engine.personalization.relevance import assess_candidate_relevance


def _build_reason(
    candidate: RawCandidate,
    user_interests: List[str],
    briefing: Optional[KoreanBriefing],
    relevance_level: str,
) -> str:
    """Generate a concrete recommendation reason in Korean.

    Uses actual source features and matched interests — NOT a generic
    template like "관심사에 맞는 소식입니다".
    """
    matched = [kw for kw in user_interests if kw.lower() in (candidate.title or "").lower() or kw.lower() in (candidate.summary or "").lower()]
    # A validated shared fact is more useful and safer than a generic template.
    # Topic relevance is explicitly comparative; it never claims the user's
    # stack can adopt another product's behaviour.
    if briefing and briefing.key_facts_ko:
        fact = briefing.key_facts_ko[0].strip()
        interest = matched[0] if matched else (user_interests[0] if user_interests else "관심 분야")
        if relevance_level == "direct":
            return f"{fact} {interest} 관련 변경 범위를 검토할 때 확인할 수 있습니다."
        return f"{fact} {interest}와 인접한 도구 변경으로, 비교·동향 파악을 위해 확인할 수 있습니다."
    features: List[str] = []

    # Source-specific features
    metrics = candidate.metrics or {}
    stars = metrics.get("stars") or metrics.get("stargazers_count")
    if stars and int(stars) > 100:
        features.append(f"GitHub 스타 {stars}개")
    comments = metrics.get("comments") or metrics.get("num_comments")
    if comments and int(comments) > 10:
        features.append(f"댓글 {comments}개")
    if candidate.source:
        features.append(f"{candidate.source} 출처")

    parts: List[str] = []
    if matched:
        parts.append(f"'{', '.join(matched[:3])}' 관심사와 관련된 소식이에요")
    if features:
        parts.append(f"({', '.join(features[:3])})")

    if not parts:
        # Fallback: use title keywords
        title_words = (candidate.title or "").split()[:3]
        if title_words:
            parts.append(f"'{' '.join(title_words)}' 주제의 최신 소식이에요")

    return ". ".join(parts) + "." if parts else ""


def personalise_rankings(
    scored_candidates: List[ScoredCandidate],
    user_interests: List[str],
    ignored_dedupe_keys: Set[str],
    tracked_dedupe_keys: Set[str],
    briefings: Dict[str, KoreanBriefing],
    *,
    display_limit: int = 5,
    validated_card_fields: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """Produce the final ranked list for a single user.

    Excludes items the user has marked as "ignored" and boosts items
    matching "tracked" interests.

    Returns a list of dicts ready for the API response, limited to
    ``display_limit`` items.
    """
    # Keep period scores intact and apply user-specific relevance only here.
    # An item with no source-grounded relationship is not backfilled merely to
    # fill a card slot.  Direct/topic are modest boosts, not hard score bands:
    # a materially important topic item can still outrank a weak direct item.
    assessed = [
        (sc, assess_candidate_relevance(sc.candidate, user_interests))
        for sc in scored_candidates
        if sc.candidate.dedupe_key not in ignored_dedupe_keys
    ]
    assessed = [(sc, relevance) for sc, relevance in assessed if relevance.level != "insufficient"]

    # Boost tracked items
    for sc, relevance in assessed:
        if sc.candidate.dedupe_key in tracked_dedupe_keys:
            sc.importance_score *= 1.2
        # Boost items with matching interests
        matched_count = sum(
            1 for kw in user_interests
            if kw.lower() in (sc.candidate.title or "").lower()
        )
        sc.importance_score += matched_count * 0.05
        sc.importance_score += 0.08 if relevance.level == "direct" else 0.02
        sc.importance_score += relevance.importance_signal

    assessed.sort(key=lambda item: item[0].importance_score, reverse=True)

    result: List[Dict[str, Any]] = []
    for i, (sc, relevance) in enumerate(assessed[:display_limit]):
        briefing = briefings.get(sc.candidate.dedupe_key)
        supplied = (validated_card_fields or {}).get(sc.candidate.dedupe_key, {})
        # Per-user fields must already be validated for this profile.  Do not
        # reuse a topic explanation as if it were direct relevance.
        if supplied.get("relevance_level") == relevance.level and supplied.get("recommendation_reason_ko"):
            reason = supplied["recommendation_reason_ko"]
        else:
            supplied = {}
            reason = _build_reason(sc.candidate, user_interests, briefing, relevance.level)
        card = {
            "rank": i + 1,
            "dedupe_key": sc.candidate.dedupe_key,
            "candidate": sc.candidate,
            "scored": sc,
            "briefing": briefing,
            "recommendation_reason_ko": reason,
            "relevance_level": relevance.level,
            "relevance_basis": relevance.basis,
        }
        if supplied:
            card.update({
                "why_it_matters_ko": supplied.get("why_it_matters_ko", ""),
                "recommended_action_ko": supplied.get("recommended_action_ko", ""),
            })
        elif briefing and briefing.key_facts_ko:
            # Safe display fallback: it asks the user to inspect the source,
            # without inventing an upgrade, deployment, or outcome claim.
            card.update({
                "why_it_matters_ko": "원문에 명시된 변경 범위를 확인할 수 있습니다.",
                "recommended_action_ko": "원문과 릴리스 노트를 확인하세요.",
            })
        result.append(card)

    return result


def get_reserve_candidates(
    scored_candidates: List[ScoredCandidate],
    displayed_keys: Set[str],
    ignored_dedupe_keys: Set[str],
    *,
    max_reserves: int = 20,
    user_interests: Optional[List[str]] = None,
) -> List[ScoredCandidate]:
    """Select reserve candidates for backfill (not currently displayed).

    These are pre-ranked but NOT pre-summarised by LLM to avoid waste.
    """
    reserves = [
        sc for sc in scored_candidates
        if sc.candidate.dedupe_key not in displayed_keys
        and sc.candidate.dedupe_key not in ignored_dedupe_keys
    ]
    if user_interests is not None:
        reserves = [
            sc for sc in reserves
            if assess_candidate_relevance(sc.candidate, user_interests).level != "insufficient"
        ]
    reserves.sort(key=lambda sc: sc.importance_score, reverse=True)
    return reserves[:max_reserves]

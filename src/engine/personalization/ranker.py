"""Per-user ranking and recommendation reason generation.

Takes scored candidates (from the shared evaluation step) and
personalises them based on the user's interests, feedback history,
and preference signals.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from src.engine.models import KoreanBriefing, RawCandidate, RecommendationReason, ScoredCandidate


def _build_reason(
    candidate: RawCandidate,
    user_interests: List[str],
    briefing: Optional[KoreanBriefing],
) -> str:
    """Generate a concrete recommendation reason in Korean.

    Uses actual source features and matched interests — NOT a generic
    template like "관심사에 맞는 소식입니다".
    """
    matched = [kw for kw in user_interests if kw.lower() in (candidate.title or "").lower() or kw.lower() in (candidate.summary or "").lower()]
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
) -> List[Dict[str, Any]]:
    """Produce the final ranked list for a single user.

    Excludes items the user has marked as "ignored" and boosts items
    matching "tracked" interests.

    Returns a list of dicts ready for the API response, limited to
    ``display_limit`` items.
    """
    # Filter out ignored items
    filtered = [
        sc for sc in scored_candidates
        if sc.candidate.dedupe_key not in ignored_dedupe_keys
    ]

    # Boost tracked items
    for sc in filtered:
        if sc.candidate.dedupe_key in tracked_dedupe_keys:
            sc.importance_score *= 1.2
        # Boost items with matching interests
        matched_count = sum(
            1 for kw in user_interests
            if kw.lower() in (sc.candidate.title or "").lower()
        )
        sc.importance_score += matched_count * 0.05

    filtered.sort(key=lambda sc: sc.importance_score, reverse=True)

    result: List[Dict[str, Any]] = []
    for i, sc in enumerate(filtered[:display_limit]):
        briefing = briefings.get(sc.candidate.dedupe_key)
        reason = _build_reason(sc.candidate, user_interests, briefing)
        result.append({
            "rank": i + 1,
            "dedupe_key": sc.candidate.dedupe_key,
            "candidate": sc.candidate,
            "scored": sc,
            "briefing": briefing,
            "recommendation_reason_ko": reason,
        })

    return result


def get_reserve_candidates(
    scored_candidates: List[ScoredCandidate],
    displayed_keys: Set[str],
    ignored_dedupe_keys: Set[str],
    *,
    max_reserves: int = 20,
) -> List[ScoredCandidate]:
    """Select reserve candidates for backfill (not currently displayed).

    These are pre-ranked but NOT pre-summarised by LLM to avoid waste.
    """
    reserves = [
        sc for sc in scored_candidates
        if sc.candidate.dedupe_key not in displayed_keys
        and sc.candidate.dedupe_key not in ignored_dedupe_keys
    ]
    reserves.sort(key=lambda sc: sc.importance_score, reverse=True)
    return reserves[:max_reserves]

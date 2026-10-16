"""Period-independent importance scoring.

Each period (daily, weekly, monthly) evaluates candidates with its own
criteria.  Weekly is NOT daily summaries aggregated; it re-scores from
raw candidates over the week range.  Same for monthly.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from src.engine.config import EngineConfig
from src.engine.evaluation.periods import period_range
from src.engine.models import Period, RawCandidate, ScoredCandidate


def _parse_date(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        return datetime.fromisoformat(d.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


def _recency_score(published: Optional[str], ref_start: date, ref_end: date) -> float:
    """Higher score for items published closer to the end of the period."""
    pub = _parse_date(published)
    if pub is None:
        return 0.3  # unknown date gets a small default
    if pub < ref_start or pub > ref_end:
        return 0.0
    span = max((ref_end - ref_start).days, 1)
    days_from_end = (ref_end - pub).days
    return max(0.0, 1.0 - (days_from_end / span) * 0.5)


def _engagement_score(metrics: Dict[str, Any]) -> float:
    """Normalised engagement from source metrics (stars, comments, etc.)."""
    stars = float(metrics.get("stars", 0) or metrics.get("stargazers_count", 0) or 0)
    comments = float(metrics.get("comments", 0) or metrics.get("num_comments", 0) or 0)
    score = math.log1p(stars) * 0.6 + math.log1p(comments) * 0.4
    return min(score / 10.0, 1.0)


def _interest_match_score(
    candidate: RawCandidate,
    user_interests: List[str],
) -> float:
    """How well the candidate matches the user's interest keywords."""
    if not user_interests:
        return 0.5
    title_lower = (candidate.title or "").lower()
    summary_lower = (candidate.summary or "").lower()
    matched = sum(
        1 for kw in user_interests
        if kw.lower() in title_lower or kw.lower() in summary_lower
    )
    return min(matched / max(len(user_interests), 1), 1.0)


# ---------------------------------------------------------------------------
# Period-specific weighting
# ---------------------------------------------------------------------------

# Each period emphasises different factors.
_PERIOD_WEIGHTS: Dict[str, Dict[str, float]] = {
    Period.DAILY: {
        "recency": 0.40,
        "engagement": 0.25,
        "interest_match": 0.35,
    },
    Period.WEEKLY: {
        "recency": 0.20,
        "engagement": 0.35,
        "interest_match": 0.45,
    },
    Period.MONTHLY: {
        "recency": 0.10,
        "engagement": 0.40,
        "interest_match": 0.50,
    },
}


def score_candidate(
    candidate: RawCandidate,
    period: str,
    ref_start: date,
    ref_end: date,
    user_interests: List[str],
) -> ScoredCandidate:
    """Score a single candidate for a specific period."""
    weights = _PERIOD_WEIGHTS.get(period, _PERIOD_WEIGHTS[Period.DAILY])

    recency = _recency_score(candidate.published_at, ref_start, ref_end)
    engagement = _engagement_score(candidate.metrics)
    interest = _interest_match_score(candidate, user_interests)

    breakdown = {
        "recency": recency,
        "engagement": engagement,
        "interest_match": interest,
    }
    total = sum(weights[k] * breakdown[k] for k in weights)

    return ScoredCandidate(
        candidate=candidate,
        period=period,
        importance_score=round(total, 4),
        score_breakdown={k: round(v, 4) for k, v in breakdown.items()},
    )


def evaluate_candidates(
    candidates: List[RawCandidate],
    period: str,
    user_interests: List[str],
    config: EngineConfig,
    *,
    reference_date: Optional[date] = None,
) -> List[ScoredCandidate]:
    """Score and rank all candidates for a period.

    Returns scored candidates sorted by descending importance, limited
    to the configured candidate cap for this period.
    """
    ref_start, ref_end = period_range(period, reference_date)
    limit_map = {
        Period.DAILY: config.evaluation.daily_candidate_limit,
        Period.WEEKLY: config.evaluation.weekly_candidate_limit,
        Period.MONTHLY: config.evaluation.monthly_candidate_limit,
    }
    limit = limit_map.get(period, 100)

    scored = [
        score_candidate(c, period, ref_start, ref_end, user_interests)
        for c in candidates
    ]
    # Filter below minimum threshold
    scored = [s for s in scored if s.importance_score >= config.evaluation.min_importance_score]
    scored.sort(key=lambda s: s.importance_score, reverse=True)

    # Assign ranks
    for i, sc in enumerate(scored[:limit]):
        sc.rank = i + 1

    return scored[:limit]

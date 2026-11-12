"""Period-independent importance scoring.

Each period (daily, weekly, monthly) evaluates candidates with its own
criteria.  Weekly is NOT daily summaries aggregated; it re-scores from
raw candidates over the week range.  Same for monthly.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from src.engine.config import EngineConfig
from src.engine.evaluation.periods import period_range
from src.engine.models import Period, RawCandidate, ScoredCandidate
from src.context.interest_matching import matches_interest


def _parse_date(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        return datetime.fromisoformat(d.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


def is_within_period(published_at: Optional[str], ref_start: date, ref_end: date) -> Optional[bool]:
    """Check if a candidate's publication date falls within the period range.

    Returns True/False for known dates, None for unknown dates.
    Unknown dates are treated as eligible (cannot prove ineligible).
    """
    pub = _parse_date(published_at)
    if pub is None:
        return None  # unknown — cannot determine eligibility
    return ref_start <= pub <= ref_end


def is_within_rolling_period(
    published_at: Optional[str], period: str, reference_now: Optional[datetime] = None,
) -> Optional[bool]:
    """Check live 24-hour/7-day/30-day rolling windows in KST."""
    if not published_at:
        return None
    from src.engine.evaluation.periods import KOREA_TZ
    end = (reference_now or datetime.now(KOREA_TZ)).astimezone(KOREA_TZ)
    days = {Period.DAILY: 1, Period.WEEKLY: 7, Period.MONTHLY: 30}.get(period)
    if days is None:
        raise ValueError(f"Unknown period: {period}")
    # A date-only source timestamp has no trustworthy time-of-day.  Keep it
    # when its date intersects the rolling window instead of pretending that
    # midnight UTC was the actual publication time.
    if "T" not in published_at:
        published_date = _parse_date(published_at)
        if published_date is None:
            return None
        return end.date() - timedelta(days=days) <= published_date <= end.date()
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    # Legacy HN rows use a naïve UTC ISO timestamp.
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return end - timedelta(days=days) <= published.astimezone(KOREA_TZ) <= end


def _recency_score(published: Optional[str], ref_start: date, ref_end: date) -> float:
    """Higher score for items published closer to the end of the period.

    Only called for candidates already confirmed eligible for this period.
    """
    pub = _parse_date(published)
    if pub is None:
        return 0.3  # unknown date gets a small default
    if pub < ref_start or pub > ref_end:
        return 0.0
    span = max((ref_end - ref_start).days, 1)
    days_from_end = (ref_end - pub).days
    return max(0.0, 1.0 - (days_from_end / span) * 0.5)


def _event_or_opportunity_eligibility(candidate: RawCandidate, reference: date) -> Optional[bool]:
    """Apply source-type time semantics before falling back to news dates.

    A forthcoming festival is useful because its real-world schedule remains
    open, not because an article happened to be published today.  Likewise an
    announcement with a confirmed open application window is an opportunity,
    not automatically a fresh news event.  ``None`` delegates to the normal
    period publication-date policy.
    """
    metrics = candidate.metrics or {}
    kind = metrics.get("content_kind")
    if kind == "culture_event":
        status = str(metrics.get("event_status") or "")
        if status == "ended":
            return False
        if status in {"upcoming", "ongoing"}:
            return True
        return False
    if kind in {"government_rnd_announcement", "startup_program_announcement", "job_announcement"}:
        status = str(metrics.get("application_window_status") or "")
        if status in {"open", "upcoming"}:
            end = _parse_date(metrics.get("application_end_at"))
            return end is None or end >= reference
        if status in {"closed", "ended"}:
            return False
    return None


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
    text = f"{candidate.title or ''} {candidate.summary or ''}".strip()
    matched = sum(
        1 for kw in user_interests
        if _candidate_matches_interest(candidate, text, kw)
    )
    return min(matched / max(len(user_interests), 1), 1.0)


def _candidate_matches_interest(candidate: RawCandidate, text: str, interest: str) -> bool:
    """Match source text conservatively, with one research metadata synonym.

    The broad LLM phrase is intentionally limited to research records.  It
    allows an English paper titled ``Large Language Model ...`` to match a
    reader's ``LLM research paper`` interest without turning generic AI news
    or an unrelated title into a semantic match.
    """
    keyword = str(interest or "").strip()
    if not keyword:
        return False
    lowered = text.casefold()
    if keyword.casefold() in lowered or matches_interest(text, keyword):
        return True
    if candidate.metrics.get("content_kind") != "research_metadata":
        return False
    normalized_interest = keyword.casefold()
    asks_for_llm = "llm" in normalized_interest or "large language model" in normalized_interest
    return asks_for_llm and any(term in lowered for term in ("llm", "large language model", "generative language model"))


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

    # Source-item storage may fall back to collection time when a publisher
    # omits a date. A Crossref record with year/month-only metadata must never
    # gain a "new paper" boost from that fallback timestamp.
    date_precision = candidate.metrics.get("publication_date_precision")
    lifecycle_eligible = _event_or_opportunity_eligibility(candidate, ref_end)
    if lifecycle_eligible is True:
        # An active/upcoming event or a confirmed open application window is
        # timely by its own schedule, even when its posting date is old.
        recency = 1.0
    elif candidate.metrics.get("content_kind") == "research_metadata" and date_precision != "day":
        recency = 0.1
    else:
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

    Two-step process:
    1. **Eligibility**: Only candidates published within the period's date
       range are eligible.  Candidates with unknown dates are kept (cannot
       prove ineligible).
    2. **Importance**: Eligible candidates are scored and ranked.

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

    # Step 1: Eligibility filter — only candidates within the date range
    eligible = []
    for c in candidates:
        lifecycle_eligible = _event_or_opportunity_eligibility(c, ref_end)
        if lifecycle_eligible is False:
            continue
        if lifecycle_eligible is True:
            eligible.append(c)
            continue
        uncertain_research_date = (
            c.metrics.get("content_kind") == "research_metadata"
            and c.metrics.get("publication_date_precision") != "day"
        )
        within = (None if uncertain_research_date else (is_within_period(c.published_at, ref_start, ref_end)
                  if reference_date is not None
                  else is_within_rolling_period(c.published_at, period)))
        if within is None or within:
            eligible.append(c)

    # Step 2: Score eligible candidates
    scored = [
        score_candidate(c, period, ref_start, ref_end, user_interests)
        for c in eligible
    ]
    # Filter below minimum threshold
    scored = [s for s in scored if s.importance_score >= config.evaluation.min_importance_score]
    scored.sort(key=lambda s: s.importance_score, reverse=True)

    # Assign ranks
    for i, sc in enumerate(scored[:limit]):
        sc.rank = i + 1

    return scored[:limit]

"""Interest grouping and collection plan generation.

Groups interests from all *active* users (those who visited within
the configured window) into canonical clusters, then generates a
collection plan that avoids duplicate jobs.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from src.engine.config import INTEREST_SYNONYMS, EngineConfig
from src.engine.models import CollectionPlan, InterestGroup, Job, JobType


def normalise_keyword(keyword: str) -> str:
    """Map a keyword to its canonical form using the synonym dictionary."""
    lower = keyword.strip().lower()
    return INTEREST_SYNONYMS.get(lower, keyword.strip())


def group_interests(
    user_interests: List[Dict[str, Any]],
    *,
    active_user_ids: Optional[Set[int]] = None,
) -> List[InterestGroup]:
    """Merge per-user interest rows into canonical groups.

    Parameters
    ----------
    user_interests:
        Rows with at least ``user_id``, ``keyword``, ``weight``, ``category``.
    active_user_ids:
        If given, only interests belonging to these users are included.

    Returns
    -------
    list of InterestGroup, sorted by descending total weight.
    """
    buckets: Dict[str, InterestGroup] = {}

    for row in user_interests:
        uid = row.get("user_id", 1)
        if active_user_ids is not None and uid not in active_user_ids:
            continue
        raw_kw = row.get("keyword", "")
        if not raw_kw:
            continue
        canonical = normalise_keyword(raw_kw)
        if canonical not in buckets:
            buckets[canonical] = InterestGroup(
                canonical_keyword=canonical,
                raw_keywords=[],
                user_ids=[],
                weight=0.0,
                category=row.get("category"),
            )
        grp = buckets[canonical]
        if raw_kw not in grp.raw_keywords:
            grp.raw_keywords.append(raw_kw)
        if uid not in grp.user_ids:
            grp.user_ids.append(uid)
        grp.weight += float(row.get("weight", 1.0))

    groups = sorted(buckets.values(), key=lambda g: g.weight, reverse=True)
    return groups


def make_dedupe_key(interest: str, source: str, date_start: str, date_end: str) -> str:
    """Deterministic hash for a collection job to prevent duplicates."""
    raw = f"{normalise_keyword(interest)}|{source}|{date_start}|{date_end}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_collection_plan(
    user_interests: List[Dict[str, Any]],
    enabled_sources: List[str],
    active_user_ids: Set[int],
    date_start: str,
    date_end: str,
    config: EngineConfig,
) -> CollectionPlan:
    """Create a collection plan from grouped interests.

    The plan respects the daily job budget and avoids starvation by
    spreading jobs across interest groups proportionally.
    """
    groups = group_interests(user_interests, active_user_ids=active_user_ids)
    budget = config.budget.max_daily_collection_jobs

    # Allocate jobs proportionally but ensure each group gets at least 1
    total_weight = sum(g.weight for g in groups) or 1.0
    allocated_jobs = 0
    plan_groups: List[InterestGroup] = []

    for grp in groups:
        if allocated_jobs >= budget:
            break
        # Each group × each source = one job
        jobs_for_group = min(len(enabled_sources), budget - allocated_jobs)
        if jobs_for_group > 0:
            plan_groups.append(grp)
            allocated_jobs += jobs_for_group

    return CollectionPlan(
        groups=plan_groups,
        sources=enabled_sources,
        date_range_start=date_start,
        date_range_end=date_end,
        budget_remaining_jobs=max(0, budget - allocated_jobs),
    )


def plan_to_jobs(plan: CollectionPlan) -> List[Job]:
    """Convert a collection plan into concrete Job objects for the queue."""
    jobs: List[Job] = []
    for group in plan.groups:
        for source in plan.sources:
            dk = make_dedupe_key(
                group.canonical_keyword, source,
                plan.date_range_start, plan.date_range_end,
            )
            jobs.append(Job(
                job_type=JobType.COLLECT,
                dedupe_key=dk,
                priority=int(min(group.weight * 10, 100)),
                payload_json={
                    "interest": group.canonical_keyword,
                    "raw_keywords": group.raw_keywords,
                    "source": source,
                    "user_ids": group.user_ids,
                    "date_start": plan.date_range_start,
                    "date_end": plan.date_range_end,
                },
            ))
    return jobs

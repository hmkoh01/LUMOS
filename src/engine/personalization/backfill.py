"""Backfill logic for when a user dismisses a briefing card.

When a user selects "이런 소식 줄이기":
1. Remove the card from their current briefing
2. Save their preference
3. Pick the next best candidate from reserves
4. If a cached Korean briefing exists, show it immediately
5. If not, schedule a generation job (don't block the user)
6. If no suitable candidate exists, don't force-fill

Does NOT trigger a new external collection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from src.engine.llm.cache import BriefingCache
from src.engine.models import KoreanBriefing, ScoredCandidate


@dataclass
class BackfillResult:
    """Outcome of a backfill attempt after dismissal."""
    replaced: bool = False
    replacement_dedupe_key: Optional[str] = None
    replacement_briefing: Optional[KoreanBriefing] = None
    needs_generation: bool = False
    dismissed_dedupe_key: str = ""
    can_undo: bool = True


def select_backfill_candidate(
    reserves: List[ScoredCandidate],
    currently_displayed: Set[str],
    ignored_keys: Set[str],
) -> Optional[ScoredCandidate]:
    """Pick the best reserve candidate not already displayed or ignored."""
    for sc in reserves:
        key = sc.candidate.dedupe_key
        if key not in currently_displayed and key not in ignored_keys:
            return sc
    return None


def perform_backfill(
    dismissed_dedupe_key: str,
    reserves: List[ScoredCandidate],
    currently_displayed: Set[str],
    ignored_keys: Set[str],
    cache: BriefingCache,
) -> BackfillResult:
    """Execute the backfill after a card dismissal.

    Returns a ``BackfillResult`` indicating what happened.
    """
    # Remove dismissed from display
    currently_displayed.discard(dismissed_dedupe_key)
    ignored_keys.add(dismissed_dedupe_key)

    candidate = select_backfill_candidate(reserves, currently_displayed, ignored_keys)

    if candidate is None:
        return BackfillResult(
            replaced=False,
            dismissed_dedupe_key=dismissed_dedupe_key,
        )

    replacement_key = candidate.candidate.dedupe_key
    cached_briefing = cache.get(replacement_key)

    return BackfillResult(
        replaced=True,
        replacement_dedupe_key=replacement_key,
        replacement_briefing=cached_briefing,
        needs_generation=cached_briefing is None,
        dismissed_dedupe_key=dismissed_dedupe_key,
        can_undo=True,
    )


def undo_dismiss(
    dismissed_dedupe_key: str,
    replacement_dedupe_key: Optional[str],
    currently_displayed: Set[str],
    ignored_keys: Set[str],
) -> None:
    """Reverse a dismiss action (undo).

    Restores the dismissed card and removes the replacement.
    """
    ignored_keys.discard(dismissed_dedupe_key)
    currently_displayed.add(dismissed_dedupe_key)
    if replacement_dedupe_key:
        currently_displayed.discard(replacement_dedupe_key)

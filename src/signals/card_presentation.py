"""Non-generative presentation policy for validated briefing titles."""

from __future__ import annotations

import re
from dataclasses import dataclass


CARD_TITLE_LIMIT = 52


@dataclass(frozen=True)
class CardTitle:
    """A title chosen without removing source-grounded meaning."""

    text: str
    display_mode: str  # single_line | two_line
    shortened: bool = False


def prepare_card_title(title: str, *, limit: int = CARD_TITLE_LIMIT) -> CardTitle:
    """Return a safe card title or retain the complete title for two lines.

    The only automatic shortening removes the redundant release announcement
    between a product/version and an already-present concrete change.  It never
    truncates a fact-bearing clause.  All other long titles remain intact and
    are a presentation concern rather than a factual validation failure.
    """
    normalized = re.sub(r"\s+", " ", (title or "").strip())
    if len(normalized) <= limit:
        return CardTitle(normalized, "single_line")

    compact = re.sub(
        r"\s*(?:버전\s*)?(?:출시|릴리스)\s*[:：\-–—]\s*",
        ", ",
        normalized,
        count=1,
    )
    if compact != normalized and len(compact) <= limit:
        return CardTitle(compact, "single_line", shortened=True)

    return CardTitle(normalized, "two_line")

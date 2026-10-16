"""Output validation for LLM-generated Korean briefings.

Checks that the generated content meets quality thresholds before
caching.  Failed validation triggers escalation to the expensive model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.engine.models import KoreanBriefing


@dataclass
class ValidationResult:
    valid: bool = True
    errors: List[str] = None
    confidence: float = 1.0

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def validate_briefing(briefing: KoreanBriefing) -> ValidationResult:
    """Validate a Korean briefing for completeness and quality."""
    errors: List[str] = []
    confidence = 1.0

    if not briefing.display_title_ko or len(briefing.display_title_ko.strip()) < 3:
        errors.append("display_title_ko is missing or too short")
        confidence -= 0.3

    if not briefing.headline_summary_ko or len(briefing.headline_summary_ko.strip()) < 10:
        errors.append("headline_summary_ko is missing or too short")
        confidence -= 0.3

    # Title should not be identical to summary
    if (
        briefing.display_title_ko
        and briefing.headline_summary_ko
        and briefing.display_title_ko.strip() == briefing.headline_summary_ko.strip()
    ):
        errors.append("title and summary are identical")
        confidence -= 0.2

    # Key facts should be a non-empty list of strings
    if not briefing.key_facts_ko:
        confidence -= 0.1
    else:
        for i, fact in enumerate(briefing.key_facts_ko):
            if not isinstance(fact, str) or len(fact.strip()) < 3:
                errors.append(f"key_facts_ko[{i}] is invalid")
                confidence -= 0.05

    return ValidationResult(
        valid=len(errors) == 0 and confidence >= 0.5,
        errors=errors,
        confidence=max(0.0, confidence),
    )


def parse_llm_briefing_response(text: str) -> Optional[KoreanBriefing]:
    """Parse an LLM response into a KoreanBriefing.

    Expects JSON with keys: display_title_ko, headline_summary_ko, key_facts_ko.
    Returns None if parsing fails.
    """
    try:
        # Handle potential markdown code blocks
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        data = json.loads(cleaned)
        return KoreanBriefing(
            display_title_ko=data.get("display_title_ko", ""),
            headline_summary_ko=data.get("headline_summary_ko", ""),
            key_facts_ko=data.get("key_facts_ko", []),
        )
    except (json.JSONDecodeError, AttributeError):
        return None

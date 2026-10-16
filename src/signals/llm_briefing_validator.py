"""Validation for LLM-generated briefing output — v2.

Checks:
  1. Structural: required fields, length limits
  2. Entity preservation: proper nouns from source → briefing
  3. Number fabrication: numbers in briefing not in source
  4. Fact grounding: cited source_quote actually appears in source text
  5. Summary-recommendation overlap
  6. Personalization: not boilerplate, fields present

Does NOT claim to verify semantic accuracy — that requires human evaluation.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


_REQUIRED_CONTENT_FIELDS = [
    "display_title_ko",
    "display_summary_ko",
    "content_type_label",
    "is_new_event",
    "key_entities",
    "limitation_ko",
]

_REQUIRED_PERSONALIZE_FIELDS = [
    "recommendation_reason_ko",
    "why_it_matters_ko",
    "recommended_action_ko",
]

# Common English words that should NOT be treated as named entities.
_COMMON_WORDS = {
    "The", "This", "That", "What", "Why", "How", "For", "And", "But", "Not",
    "Its", "Has", "Are", "Was", "With", "From", "Show", "Ask", "New", "All",
    "Now", "Our", "May", "Can", "Is", "You", "Need", "Key", "It", "In",
    "State", "Survey", "Build", "Using", "Settings", "Enterprise", "After",
    "Breaking", "Major", "Companies", "Every", "Best", "Way", "Expanded",
    "Revisited", "Agentic", "Workflows", "Do", "Does", "Did", "Will",
    "An", "Be", "By", "Or", "So", "Up", "On", "At", "To", "Of", "As",
    "No", "We", "He", "She", "My", "Your", "Their", "Into", "Also",
    "First", "Most", "More", "Over", "Some", "Such", "Than", "Then",
    "Here", "There", "When", "Where", "Been", "Being", "Have", "Had",
    "About", "Each", "Made", "Find", "Know", "Take", "Want", "Many",
    "These", "Just", "Only", "Very", "Should", "Would", "Could", "Still",
    "Year", "Years", "Day", "Time", "Data", "Based", "Other",
}


def validate_content_briefing(
    briefing: Dict[str, Any],
    source_item: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate a content briefing against its source item."""
    issues: List[str] = []
    warnings: List[str] = []
    checks: Dict[str, Any] = {}

    # 1. Required fields
    missing = [f for f in _REQUIRED_CONTENT_FIELDS if f not in briefing or briefing[f] is None]
    checks["required_fields"] = {"pass": not missing, "missing": missing}
    if missing:
        issues.append(f"필수 필드 누락: {missing}")

    # 2. Title length
    title = briefing.get("display_title_ko", "")
    checks["title_length"] = {"length": len(title), "pass": 0 < len(title) <= 80}
    if len(title) > 80:
        warnings.append(f"제목 과장: {len(title)}자 (목표 <=52)")
    if not title:
        issues.append("빈 제목")

    # 3. Summary length
    summary = briefing.get("display_summary_ko", "")
    checks["summary_length"] = {"length": len(summary), "pass": 0 < len(summary) <= 300}
    if len(summary) > 300:
        warnings.append(f"요약 과장: {len(summary)}자 (목표 <=200)")
    if not summary:
        issues.append("빈 요약")

    # 4. Entity preservation
    source_text = f"{source_item.get('title', '')} {source_item.get('summary', '')}"
    entities = _extract_entities(source_text)
    briefing_text = _collect_briefing_text(briefing)

    preserved, missing_entities = [], []
    for entity in entities:
        if entity.lower() in briefing_text.lower():
            preserved.append(entity)
        else:
            missing_entities.append(entity)

    checks["entity_preservation"] = {
        "source_entities": entities,
        "preserved": preserved,
        "missing": missing_entities,
        "ratio": len(preserved) / max(len(entities), 1),
        "pass": len(missing_entities) <= len(entities) * 0.5,
    }
    if missing_entities:
        warnings.append(f"고유명사 미보존: {missing_entities}")

    # 5. Number fabrication
    source_numbers = set(_extract_numbers(source_text))
    briefing_numbers = set(_extract_numbers(briefing_text))
    fabricated = {n for n in (briefing_numbers - source_numbers) if not _is_trivial_number(n)}
    checks["number_fabrication"] = {
        "source_numbers": list(source_numbers),
        "briefing_numbers": list(briefing_numbers),
        "fabricated": list(fabricated),
        "pass": len(fabricated) == 0,
    }
    if fabricated:
        issues.append(f"원문에 없는 수치: {fabricated}")

    # 6. Fact grounding verification
    grounded_facts = briefing.get("grounded_facts", [])
    if grounded_facts:
        grounding_results = _verify_grounding(grounded_facts, source_text)
        checks["fact_grounding"] = grounding_results
        ungrounded = [r for r in grounding_results["details"] if not r["quote_found"]]
        if ungrounded:
            warnings.append(f"근거 미확인 주장 {len(ungrounded)}건 (LLM이 인용한 문구가 원문에 없음)")
    else:
        checks["fact_grounding"] = {"verified": 0, "unverified": 0, "details": []}

    # 7. Summary-recommendation overlap
    rec = briefing.get("recommendation_reason_ko", "")
    if rec and summary:
        overlap = _text_overlap_ratio(summary, rec)
        checks["summary_rec_overlap"] = {"overlap_ratio": round(overlap, 2), "pass": overlap < 0.6}
        if overlap >= 0.6:
            warnings.append(f"요약-추천 중복 {overlap:.0%}")

    valid = len(issues) == 0
    return {"valid": valid, "issues": issues, "warnings": warnings, "checks": checks}


def validate_personalization(
    personalization: Dict[str, Any],
    content_briefing: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate personalization output."""
    issues: List[str] = []
    warnings: List[str] = []
    checks: Dict[str, Any] = {}

    missing = [f for f in _REQUIRED_PERSONALIZE_FIELDS if f not in personalization or not personalization[f]]
    checks["required_fields"] = {"pass": not missing, "missing": missing}
    if missing:
        issues.append(f"개인화 필드 누락: {missing}")

    rec = personalization.get("recommendation_reason_ko", "")
    _BOILERPLATE = [
        re.compile(r".+분야의 .+를 다뤄.+추천했어요"),
        re.compile(r".+분야의 최근 변화를 다뤄"),
        re.compile(r"관심사 .+와 관련된 자료예요"),
    ]
    is_boilerplate = any(p.search(rec) for p in _BOILERPLATE)
    checks["not_boilerplate"] = {"pass": not is_boilerplate, "text": rec[:100]}
    if is_boilerplate:
        warnings.append("추천 이유가 범용 템플릿과 유사")

    confidence = personalization.get("relevance_confidence", "")
    checks["has_confidence"] = {"pass": confidence in ("high", "medium", "low"), "value": confidence}

    return {"valid": len(issues) == 0, "issues": issues, "warnings": warnings, "checks": checks}


# ---------------------------------------------------------------------------
# Fact grounding verification
# ---------------------------------------------------------------------------
def _verify_grounding(
    grounded_facts: List[Dict[str, Any]],
    source_text: str,
) -> Dict[str, Any]:
    """Check if LLM-cited source_quotes actually appear in the source text.

    This does NOT verify that the quote supports the claim — only that the
    quoted text exists in the original. Semantic verification requires human eval.
    """
    source_lower = source_text.lower()
    details = []
    verified = 0
    unverified = 0

    for fact in grounded_facts:
        quote = fact.get("source_quote", "").strip()
        claim = fact.get("claim", "").strip()
        fact_type = fact.get("type", "unknown")

        if not quote:
            details.append({
                "claim": claim, "source_quote": "", "quote_found": False,
                "type": fact_type, "note": "인용 없음",
            })
            unverified += 1
            continue

        # Fuzzy match: check if significant words from quote appear in source
        quote_words = set(w for w in quote.lower().split() if len(w) > 2)
        if not quote_words:
            details.append({
                "claim": claim, "source_quote": quote, "quote_found": False,
                "type": fact_type, "note": "인용이 너무 짧음",
            })
            unverified += 1
            continue

        # Check: at least 60% of quote words in source text
        found_words = sum(1 for w in quote_words if w in source_lower)
        match_ratio = found_words / len(quote_words)
        quote_found = match_ratio >= 0.6

        details.append({
            "claim": claim,
            "source_quote": quote[:100],
            "quote_found": quote_found,
            "match_ratio": round(match_ratio, 2),
            "type": fact_type,
        })

        if quote_found:
            verified += 1
        else:
            unverified += 1

    return {"verified": verified, "unverified": unverified, "details": details}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _collect_briefing_text(briefing: Dict[str, Any]) -> str:
    """Gather all text fields for searching."""
    parts = [
        briefing.get("display_title_ko", ""),
        briefing.get("display_summary_ko", ""),
        " ".join(briefing.get("key_entities", [])),
    ]
    for fact in briefing.get("grounded_facts", []):
        parts.append(fact.get("claim", ""))
    for fact in briefing.get("key_facts", []):
        if isinstance(fact, str):
            parts.append(fact)
    return " ".join(parts)


def _extract_entities(text: str) -> List[str]:
    """Extract proper nouns from text, filtering common English words."""
    entities = []
    for match in re.finditer(r'\b([A-Z][A-Za-z0-9]*(?:[-/][A-Za-z0-9]+)*)\b', text):
        word = match.group(1)
        if len(word) >= 2 and word not in _COMMON_WORDS:
            entities.append(word)

    # Korean quoted names
    for match in re.finditer(
        r"['\u2018\u2019\u201c\u201d]([^'\u2018\u2019\u201c\u201d]+)['\u2018\u2019\u201c\u201d]",
        text,
    ):
        entities.append(match.group(1))

    seen = set()
    unique = []
    for e in entities:
        if e.lower() not in seen:
            seen.add(e.lower())
            unique.append(e)
    return unique


def _extract_numbers(text: str) -> List[str]:
    numbers = []
    for match in re.finditer(r'\b(\d[\d,.]*\d|\d)\b', text):
        numbers.append(match.group(1).replace(",", ""))
    return numbers


def _is_trivial_number(num_str: str) -> bool:
    try:
        n = float(num_str)
        return (2020 <= n <= 2030) or n <= 5
    except ValueError:
        return False


def _text_overlap_ratio(text_a: str, text_b: str) -> float:
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / min(len(words_a), len(words_b))

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

from src.signals.card_presentation import prepare_card_title


_PRODUCT_AVAILABILITY_LANGUAGE = re.compile(
    r"(?:\ucd9c\uc2dc|public(?:ly)?\s+available|product\s+release|\brelease\b|\blaunch\b)", re.I
)
_SOURCE_AVAILABILITY_EVIDENCE = re.compile(
    r"(?:public(?:ly)?\s+available|product\s+release|\breleased\b|\blaunched\b|\uCD9C\uC2DC)", re.I
)


_REQUIRED_CONTENT_FIELDS = [
    "display_title_ko",
    "display_summary_ko",
    "content_type_label",
    "is_new_event",
    "key_entities",
    "limitation_ko",
]

_REQUIRED_PERSONALIZE_FIELDS = [
    "source_facts_ko",
    "user_relevance_ko",
    "recommendation_reason_ko",
    "why_it_matters_ko",
    "recommended_action_ko",
]

# Outcome claims require explicit evidence in the cited source, rather than
# mere keyword overlap with a feature description.
_EFFECT_PATTERNS = [
    ("performance", re.compile(r"(?:성능|처리\s*속도|속도).{0,12}(?:향상|개선|최적화|빨라)"),
     re.compile(r"(?:performance|latency|throughput|faster|speed).{0,40}(?:improv|reduc|faster|increase)|(?:improv|reduc|faster|increase).{0,40}(?:performance|latency|throughput|speed)", re.I)),
    ("stability", re.compile(r"(?:안정성|신뢰성).{0,16}(?:향상|개선|보장)|(?:안정화|안정적으로)"),
     re.compile(r"(?:stability|reliability).{0,40}(?:improv|enhanc|guarantee)|(?:improv|enhanc|guarantee).{0,40}(?:stability|reliability)", re.I)),
    ("bug_fix", re.compile(r"(?:오류|버그).{0,12}(?:해결|수정|제거|방지)"),
     re.compile(r"(?:fix|resolve|prevent).{0,40}(?:error|bug)|(?:error|bug).{0,40}(?:fix|resolve|prevent)", re.I)),
    ("optimization", re.compile(r"(?:최적화|효율화)"),
     re.compile(r"(?:optimi[sz]|efficien)", re.I)),
    ("guarantee", re.compile(r"(?:보장|반드시|확실하게).{0,12}(?:개선|향상|해결|방지)?"),
     re.compile(r"(?:guarantee|ensure|always|prevent)", re.I)),
]

_GENERIC_RECOMMENDATION_START = re.compile(
    r"^\s*(?:요청하신|관심\s*분야의|AI\s*에이전트\s*관련|개발\s*분야의).{0,100}(?:소식|뉴스)(?:입니다|이에요)",
)

_GENERIC_RELEASE_TITLE = re.compile(
    r"^\s*[A-Za-z][A-Za-z0-9 ._-]*(?:v?\d[\w.-]*)?\s*(?:버전\s*)?(?:출시|릴리스)\s*$",
)

_DEPLOYMENT_DIRECTIVE = re.compile(r"(?:업데이트|도입|적용|마이그레이션)(?:하세요|하십시오|해보세요)")

_GENERIC_CARD_TITLE = re.compile(
    r"(?:\uc18c\uac1c|\uae30\ub2a5\s*\uc18c\uac1c|\ud50c\ub7ab\ud3fc\s*\uc18c\uac1c|\ub9ac\ud3ec\uc9c0\ud1a0\ub9ac\s*\uc18c\uac1c|\uad00\ub828\s*\uc815\ubcf4|\ucc38\uace0\ud560\s*\ub9cc\ud55c)", re.I,
)
_REPOSITORY_DISCOVERY_TITLE = re.compile(
    r"(?:\uc800\uc7a5\uc18c\s*\ubc1c\uacac|\ud504\ub85c\uc81d\ud2b8\s*\uc800\uc7a5\uc18c|\ub9ac\ud3ec\uc9c0\ud1a0\ub9ac\s*\ubc1c\uacac)", re.I,
)
_NEWS_EVENT_LANGUAGE = re.compile(
    r"(?:\ucd9c\uc2dc|\uacf5\uac1c|\ubc1c\ud45c|\uc0c8\ub85c\uc6b4\s*\ubc84\uc804|\ub9b4\ub9ac\uc988|\ub7f0\uce6d|\brelease\b|\blaunch\b)", re.I,
)
_GENERIC_PERSONALIZATION = re.compile(
    r"(?:\uc778\uc811\s*\uc8fc\uc81c(?:\s*\uad00\uc810)?|\uc778\uc811\ud55c\s*\ub3c4\uad6c\s*\ubcc0\uacbd|\uc9c1\uc811\uc801\s*\uad00\ub828\uc131\uc774\s*\ub0ae\uc9c0\ub9cc|\ud504\ub85c\uc81d\ud2b8\s*\uc800\uc7a5\uc18c\s*\uad6c\uc870\ub97c?\s*\uac80\ud1a0|\uad00\ub828\s*\uc790\ub8cc(?:\ub97c|\uc744)?\s*(?:\uac80\ud1a0|\ud655\uc778)(?:\ud560|\ud574\ubcfc)\s*\uc218\s*\uc788\uc2b5\ub2c8\ub2e4|\uac80\ud1a0\ud560\s*\ub9cc\ud569\ub2c8\ub2e4|\ucc38\uace0\ud560\s*\ub9cc\ud569\ub2c8\ub2e4)(?:[.!\s]|$)",
    re.I,
)
_EMPTY_RECOMMENDATION_ENDING = re.compile(
    r"(?:\uc6d0\ubb38(?:\uc744|\uc5d0\uc11c)?(?:\s*\uae30\uc900\uc73c\ub85c)?\s*(?:\ud655\uc778|\uac80\ud1a0)\ud560\s*\uc218\s*\uc788\uc2b5\ub2c8\ub2e4|\ucc38\uace0\ud560\s*\uc218\s*\uc788\uc2b5\ub2c8\ub2e4)\s*[.!]?\s*$",
    re.I,
)
_DECISION_CUE = re.compile(
    r"(?:\ube44\uad50|\ud310\ub2e8|\uc120\ud0dd|\uc124\uacc4|\uad6c\uc131|\ud655\uc7a5|\ud638\ud658|\uc758\uc874\uc131|\uae30\ub85d|\ucc98\ub9ac|\uc9c1\ubb34|\uc9c0\uc6d0\s*\ub300\uc0c1|\uc811\uc218|\ub9c8\uac10|\uc2e0\uccad|\uc77c\uc815|\uc7a5\uc18c|\uc9c0\uc5ed|\uacf5\uc2dc|\ubcc0\uacbd\s*\ubc94\uc704|\uae30\ub2a5\s*\ubc94\uc704)",
    re.I,
)

# These are not forbidden words. They need a nearby plain-language meaning
# so a reader unfamiliar with developer vocabulary can understand the card.
_JARGON_EXPLANATIONS = (
    (re.compile(r"(?:\ub80c\ub354\ub9c1|rendering)", re.I), re.compile(r"(?:\ube44\ub514\uc624|\uc601\uc0c1|\ud654\uba74).{0,12}(?:\ub9cc\ub4e4|\ubcc0\ud658)|(?:\ub9cc\ub4e4|\ubcc0\ud658).{0,12}(?:\ube44\ub514\uc624|\uc601\uc0c1|\ud654\uba74)", re.I), "렌더링의 쉬운 설명 없음"),
    (re.compile(r"(?:\ud504\ub808\uc784\uc6cc\ud06c|framework)", re.I), re.compile(r"(?:\ub3c4\uad6c\s*(?:\ubaa8\uc74c|\ubb36\uc74c|\ud2c0)|\ub9cc\ub4e4\s*\ub54c\s*\uc4f0\ub294\s*\ub3c4\uad6c)", re.I), "프레임워크의 쉬운 설명 없음"),
    (re.compile(r"(?:\uad00\uce21\s*\uac00\ub2a5\uc131|observability)", re.I), re.compile(r"(?:\uc2e4\ud589\s*\uc0c1\ud0dc|\uc624\ub958|\ubb38\uc81c\s*\uc6d0\uc778).{0,16}(?:\uc0b4\ud53c|\ucd94\uc801|\ud655\uc778)|(?:\uc0b4\ud53c|\ucd94\uc801|\ud655\uc778).{0,16}(?:\uc2e4\ud589\s*\uc0c1\ud0dc|\uc624\ub958|\ubb38\uc81c\s*\uc6d0\uc778)", re.I), "관측 가능성의 쉬운 설명 없음"),
    (re.compile(r"(?:\ucee8\ud14d\uc2a4\ud2b8|context)", re.I), re.compile(r"(?:\uc774\uc804\s*\uc791\uc5c5\s*(?:\uae30\ub85d|\uc815\ubcf4)|\uc138\uc158\s*(?:\uae30\ub85d|\uc815\ubcf4))", re.I), "컨텍스트의 쉬운 설명 없음"),
)

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
    title_presentation = prepare_card_title(title)
    checks["title_length"] = {"length": len(title), "pass": 0 < len(title) <= 52}
    checks["title_presentation"] = {
        "display_title_ko": title_presentation.text,
        "display_mode": title_presentation.display_mode,
        "shortened": title_presentation.shortened,
        "pass": bool(title_presentation.text),
    }
    if len(title) > 52:
        # A title length is a card layout decision, not evidence that its
        # grounded facts are wrong.  Keep the validated content and render the
        # complete title across two lines when no safe shortening exists.
        warnings.append(f"제목 2줄 표시: {len(title)}자 (단일 줄 목표 52자)")
    if not title:
        issues.append("빈 제목")

    # These phrases communicate neither an event nor a useful decision point.
    # Reject rather than invent a replacement: deterministic rewriting could
    # introduce a fact the source did not state.
    generic_title = bool(_GENERIC_CARD_TITLE.search(title))
    checks["title_has_reader_value"] = {"pass": not generic_title}
    if generic_title:
        issues.append("card title is generic rather than event- or information-led")

    # A GitHub repository search is discovery metadata. It must neither be
    # presented as a news event nor start the reader-facing title with an
    # unfamiliar owner/repository identifier. The original title remains in
    # provenance, so rejecting this output never loses source detail.
    content_kind = str(source_item.get("content_kind") or (source_item.get("metrics") or {}).get("content_kind") or "")
    source_title = str(source_item.get("title") or "").strip()
    title_starts_with_source = bool(source_title and title.casefold().startswith(source_title.casefold()))
    # GitHub search candidates historically did not all carry content_kind.
    # An owner/repository-shaped title is still discovery metadata, so apply
    # the same reader-facing policy without guessing that it is a release.
    repository_like_source = bool(
        str(source_item.get("source") or "").casefold() == "github"
        and re.fullmatch(r"[^/\s]+/[^/\s]+", source_title)
    )
    repository_violation = (
        (content_kind == "repository_discovery" or repository_like_source)
        and (title_starts_with_source or _GENERIC_CARD_TITLE.search(title) or _REPOSITORY_DISCOVERY_TITLE.search(title) or
             (briefing.get("is_new_event") is True and _NEWS_EVENT_LANGUAGE.search(title)))
    )
    checks["repository_presentation"] = {
        "pass": not repository_violation,
        "content_kind": content_kind,
        "repository_like_source": repository_like_source,
        "title_starts_with_source": title_starts_with_source,
    }
    if repository_violation:
        issues.append("repository discovery cannot be presented as a generic or new-event news card")

    # An internal engineering article can describe a deployed internal system;
    # that is not evidence of a public product release.  "Introduces" remains
    # allowed, while explicit availability wording requires source support.
    source_text = f"{source_item.get('title', '')} {source_item.get('summary', '')}"
    availability_claimed = bool(_PRODUCT_AVAILABILITY_LANGUAGE.search(title))
    availability_supported = bool(_SOURCE_AVAILABILITY_EVIDENCE.search(source_text))
    checks["availability_language"] = {
        "pass": not availability_claimed or availability_supported,
        "claimed": availability_claimed,
        "source_supported": availability_supported,
    }
    if availability_claimed and not availability_supported:
        issues.append("unverified public-product availability language in title")

    # 3. Summary length
    summary = briefing.get("display_summary_ko", "")
    checks["summary_length"] = {"length": len(summary), "pass": 0 < len(summary) <= 300}
    if len(summary) > 300:
        warnings.append(f"요약 과장: {len(summary)}자 (목표 <=200)")
    if not summary:
        issues.append("빈 요약")

    reader_text = f"{title} {summary}"
    unexplained_jargon = [
        message for term, explanation, message in _JARGON_EXPLANATIONS
        if term.search(reader_text) and not explanation.search(reader_text)
    ]
    checks["reader_language"] = {
        "pass": not unexplained_jargon,
        "unexplained": unexplained_jargon,
    }
    if unexplained_jargon:
        issues.append("일반 독자를 위한 전문 용어 설명 부족: " + ", ".join(unexplained_jargon))

    # 4. Entity preservation
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
    fabricated = {
        n for n in (briefing_numbers - source_numbers)
        if not _is_trivial_number(n) and not _is_version_component(n, source_numbers)
    }
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
        overstated = [r for r in grounding_results["details"] if not r["meaning_supported"]]
        if ungrounded:
            warnings.append(f"근거 미확인 주장 {len(ungrounded)}건 (LLM이 인용한 문구가 원문에 없음)")
        if overstated:
            issues.append(f"원문 근거를 넘어선 효과 주장 {len(overstated)}건")
    else:
        checks["fact_grounding"] = {"verified": 0, "unverified": 0, "details": []}

    # A release title must surface a confirmed change when such facts exist;
    # otherwise the title has no briefing value beyond the source title.
    generic_release_title = bool(_GENERIC_RELEASE_TITLE.fullmatch(title))
    title_has_grounded_change = bool(grounded_facts)
    checks["title_change_specificity"] = {
        "pass": not (generic_release_title and title_has_grounded_change),
        "generic_release_title": generic_release_title,
        "grounded_change_available": title_has_grounded_change,
    }
    if generic_release_title and title_has_grounded_change:
        issues.append("제목이 확인된 핵심 변경을 전달하지 않음")

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
    registered_interests: List[str] | None = None,
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
    generic_personalization = bool(_GENERIC_PERSONALIZATION.search(rec))
    checks["not_boilerplate"] = {
        "pass": not is_boilerplate and not generic_personalization,
        "text": rec[:100],
        "generic_personalization": generic_personalization,
    }
    if is_boilerplate or generic_personalization:
        issues.append("추천 이유가 구체적인 관심사·원문 연결 근거 없이 상투적임")

    confidence = personalization.get("relevance_confidence", "")
    checks["has_confidence"] = {"pass": confidence in ("high", "medium", "low"), "value": confidence}

    evidence = " ".join(
        fact.get("source_quote", "") for fact in content_briefing.get("grounded_facts", [])
    )
    effect_claims = _unsupported_effect_claims(
        " ".join([
            personalization.get("source_facts_ko", ""),
            personalization.get("user_relevance_ko", ""), rec,
            personalization.get("why_it_matters_ko", ""),
            personalization.get("recommended_action_ko", ""),
        ]), evidence,
    )
    checks["effect_claim_fidelity"] = {"pass": not effect_claims, "unsupported": effect_claims}
    if effect_claims:
        issues.append("원문 근거 없이 효과를 단정한 추천 문장")

    directive_text = " ".join([
        rec, personalization.get("why_it_matters_ko", ""), personalization.get("recommended_action_ko", ""),
    ])
    deployment_directive = bool(_DEPLOYMENT_DIRECTIVE.search(directive_text))
    checks["no_unverified_deployment_directive"] = {"pass": not deployment_directive}
    if deployment_directive:
        issues.append("사용자 환경 확인 없이 배포·업데이트를 지시한 문장")

    context_first = not bool(_GENERIC_RECOMMENDATION_START.search(rec))
    checks["specific_context_first"] = {"pass": context_first, "text": rec[:100]}
    if not context_first:
        warnings.append("추천 이유가 일반적인 분야 소개로 시작함")

    # A recommendation must identify at least one source-specific anchor when
    # the content has named entities or versioned facts.  This prevents a
    # factually safe but unhelpfully generic topic recommendation such as
    # "related tooling is worth reviewing".
    anchors = []
    for entity in content_briefing.get("key_entities", []):
        normalized = str(entity).strip()
        if len(normalized) >= 3:
            anchors.append(normalized)
    anchors.extend(re.findall(r"\bv?\d+(?:\.\d+)+\b", " ".join([
        personalization.get("source_facts_ko", ""),
        content_briefing.get("display_title_ko", ""),
    ])))
    anchors = list(dict.fromkeys(anchors))
    detail_anchor_present = not anchors or any(anchor.lower() in rec.lower() for anchor in anchors)
    checks["source_detail_anchor"] = {"pass": detail_anchor_present, "anchors": anchors[:6]}
    if not detail_anchor_present:
        issues.append("추천 이유에 원문 변경을 식별할 구체적 근거가 없음")

    # A caller with registered interests can reject a generic sentence that
    # merely repeats the card. Historical callers omit this optional argument
    # and therefore retain their original validation behaviour.
    if registered_interests is not None:
        profile_text = " ".join((
            str(personalization.get("user_relevance_ko", "")), rec,
        )).casefold()
        interest_terms = []
        for interest in registered_interests:
            normalized = " ".join(str(interest or "").casefold().split())
            if not normalized:
                continue
            interest_terms.append(normalized)
            interest_terms.extend(
                part for part in re.split(r"[\s/,-]+", normalized)
                if (part.isascii() and len(part) >= 3) or (not part.isascii() and len(part) >= 2)
            )
        interest_terms = list(dict.fromkeys(interest_terms))
        matched_interest_terms = [term for term in interest_terms if term in profile_text]
        interest_specific = bool(matched_interest_terms)
        checks["interest_specificity"] = {
            "pass": interest_specific,
            "matched_terms": matched_interest_terms[:4],
        }
        if not interest_specific:
            issues.append("recommendation reason has no registered-interest-specific connection")

        empty_ending = bool(_EMPTY_RECOMMENDATION_ENDING.search(rec))
        decision_cue = bool(_DECISION_CUE.search(rec))
        checks["recommendation_usefulness"] = {
            "pass": not empty_ending and decision_cue,
            "empty_ending": empty_ending,
            "decision_cue": decision_cue,
        }
        if empty_ending or not decision_cue:
            issues.append("추천 이유가 사용자가 살필 구체적인 판단·비교 지점을 설명하지 않음")

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
                "claim": claim, "source_quote": "", "quote_found": False, "meaning_supported": False,
                "type": fact_type, "note": "인용 없음",
            })
            unverified += 1
            continue

        # Fuzzy match: check if significant words from quote appear in source
        quote_words = set(w for w in quote.lower().split() if len(w) > 2)
        if not quote_words:
            details.append({
                "claim": claim, "source_quote": quote, "quote_found": False, "meaning_supported": False,
                "type": fact_type, "note": "인용이 너무 짧음",
            })
            unverified += 1
            continue

        # Check: at least 60% of quote words in source text
        found_words = sum(1 for w in quote_words if w in source_lower)
        match_ratio = found_words / len(quote_words)
        quote_found = match_ratio >= 0.6
        unsupported_effects = _unsupported_effect_claims(claim, quote)

        details.append({
            "claim": claim,
            "source_quote": quote[:100],
            "quote_found": quote_found,
            "meaning_supported": quote_found and not unsupported_effects,
            "unsupported_effects": unsupported_effects,
            "match_ratio": round(match_ratio, 2),
            "type": fact_type,
        })

        if quote_found:
            verified += 1
        else:
            unverified += 1

    return {"verified": verified, "unverified": unverified, "details": details}


def _unsupported_effect_claims(claim: str, source_evidence: str) -> List[str]:
    """Find outcome claims that the cited evidence does not explicitly state."""
    unsupported = []
    for category, claim_pattern, evidence_pattern in _EFFECT_PATTERNS:
        matches = list(claim_pattern.finditer(claim))
        asserted = any(
            not re.search(r"(?:않|없)", claim[match.end():match.end() + 48])
            for match in matches
        )
        if asserted and not evidence_pattern.search(source_evidence):
            unsupported.append(category)
    return unsupported


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


def _is_version_component(num_str: str, source_numbers: set) -> bool:
    """Do not flag ``24`` when a source version already contains ``24.0``."""
    return any(source.startswith(f"{num_str}.") or source.endswith(f".{num_str}") for source in source_numbers)


def _text_overlap_ratio(text_a: str, text_b: str) -> float:
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / min(len(words_a), len(words_b))

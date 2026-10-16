"""Offline briefing quality evaluator — v2.

Designed to measure whether briefings are genuinely readable and faithful,
not to produce high scores.  Each check explicitly documents what it can
and cannot measure, and never counts unevaluated items as successes.

Evaluation dimensions (7 + cross-briefing):
  1. korean_readability    — 쉬운 한국어 이해도        [auto-partial + human]
  2. factual_fidelity      — 원문 사실 충실도          [auto-partial + human]
  3. novelty_detection     — 새로운 사건 여부 판별     [auto-partial + human]
  4. date_accuracy         — 날짜 의미 정확성          [auto]
  5. recommendation_detail — 추천 이유의 구체성        [auto + human]
  6. repetition            — 중복·반복 표현            [auto]
  7. interest_relevance    — 관심사별 적합성           [auto-partial + human]
"""

import re
from typing import Any, Dict, List, Optional


# ── Keyword synonym map (EN ↔ KO) for interest matching ──────────────

_KEYWORD_SYNONYMS = {
    "ai agent": ["ai 에이전트", "ai에이전트", "ai agent", "인공지능 에이전트", "ai 상담원"],
    "생산성 툴": ["생산성 툴", "생산성 도구", "productivity tool", "productivity"],
    "개발자 도구": ["개발자 도구", "developer tool", "dev tool", "개발 도구"],
    "업무 자동화": ["업무 자동화", "workflow automation", "자동화", "automation"],
    "정보보안": ["정보보안", "보안", "security", "사이버 보안", "cyber security"],
    "개인정보 보호": ["개인정보 보호", "개인정보", "privacy", "비식별화"],
    "한국어 nlp": ["한국어 nlp", "한국어 자연어", "korean nlp", "한국어 언어 모델", "한국어 모델"],
    "스타트업": ["스타트업", "startup", "창업"],
    "github 트렌드": ["github 트렌드", "github trend", "깃허브"],
}


def _normalize_keyword(kw: str) -> str:
    return kw.strip().lower()


def _keyword_variants(keyword: str) -> List[str]:
    """Return all known variants of a keyword for matching."""
    norm = _normalize_keyword(keyword)
    variants = [norm]
    for canonical, synonyms in _KEYWORD_SYNONYMS.items():
        if norm == canonical or norm in [s.lower() for s in synonyms]:
            variants.extend(s.lower() for s in synonyms)
            variants.append(canonical)
    return list(set(variants))


# ── Known template patterns (for detecting non-specific recommendations) ──

_RECOMMENDATION_TEMPLATES = [
    # The standard _recommendation_reason_ko() output pattern
    re.compile(r".+분야의 .+를 다뤄, 최근 흐름이 실제 적용이나 시장 변화로 어떻게 이어지는지 판단하는 데 도움이 될 만해 추천했어요\.$"),
]

_WHY_MATTERS_TEMPLATES = [
    re.compile(r"^관심사 .+와 관련된 자료예요\. 실제로 도움이 되는지는 제공된 설명과 원문을 확인해주세요\.$"),
]

_ACTION_TEMPLATES = [
    re.compile(r".+ 흐름을 계속 추적할지 원문을 보고 판단해보세요\.$"),
    re.compile(r".+이 실제 업무나 제품 기능으로 이어지는 사례인지 확인해보세요\.$"),
    re.compile(r"비슷한 .+ 사례를 2~3개 더 모아 흐름이 이어지는지 비교해보세요\.$"),
    re.compile(r"^원문을 빠르게 훑고 계속 추적할 만한 흐름인지 표시해보세요\.$"),
]


# ── 1. Korean readability ────────────────────────────────────────────

_MT_ARTIFACTS = [
    # Common MyMemory / MT awkward patterns
    re.compile(r"장기 기억 장치", re.I),        # "long-term memory" → awkward
    re.compile(r"그것은? (?:했|한|합)"),          # literal "it did" calque
    re.compile(r"(?:되었|되어) ?(?:졌|집니다)"),  # double passive
    re.compile(r"있습니다\. .{0,10}있습니다"),     # repeated -습니다 endings
    re.compile(r"위한 위한"),                     # doubled postpositions
    re.compile(r"(?:을|를) (?:을|를)"),
]


def check_korean_readability(briefing: Dict[str, Any]) -> Dict[str, Any]:
    """Automated format checks + MT artifact detection.

    MEASURES: title/summary length, HTML residue, sentence length,
              known machine-translation artifacts.
    CANNOT MEASURE: natural expression quality, contextual appropriateness,
                    whether the Korean reads like a human wrote it.
    """
    issues = []
    warnings = []  # Suspicious but not definitively wrong
    title = briefing.get("display_title_ko", "")
    summary = briefing.get("display_summary_ko", "")

    # --- Format checks (definitive) ---
    if not title or title == "제목 없는 소식":
        issues.append("제목 누락 또는 폴백 사용")
    elif len(title) > 55:
        issues.append(f"제목 길이 초과: {len(title)}자")

    if not summary:
        issues.append("요약 누락")
    elif len(summary) > 520:
        issues.append(f"요약 길이 초과: {len(summary)}자")

    if re.search(r"<[a-z/][^>]*>", title + summary, re.I):
        issues.append("HTML 태그 잔존")

    # Sentence length
    if summary:
        sents = [s.strip() for s in re.split(r"[.!?]\s+", summary) if len(s.strip()) > 5]
        if sents:
            avg_len = sum(len(s) for s in sents) / len(sents)
            if avg_len > 100:
                issues.append(f"평균 문장 길이 과다: {avg_len:.0f}자")

    # --- MT artifact detection (suspicious, not definitive) ---
    combined = f"{title} {summary}"
    for pattern in _MT_ARTIFACTS:
        match = pattern.search(combined)
        if match:
            warnings.append(f"번역체 의심: '{match.group()}'")

    # Check for untranslated English in Korean-original text
    if briefing.get("original_language") == "ko":
        long_en = re.findall(r"[A-Za-z]{30,}", combined)
        if long_en:
            issues.append(f"한국어 원문에 긴 영문: {long_en[0][:40]}...")

    # For translated text: check if large portions remain in English
    if briefing.get("original_language") == "en":
        korean_chars = sum(1 for c in combined if "\uac00" <= c <= "\ud7a3")
        ascii_chars = sum(1 for c in combined if c.isascii() and c.isalpha())
        if ascii_chars > 0 and korean_chars < ascii_chars * 0.3:
            warnings.append("번역 불완전: 한국어 비율 낮음")

    format_score = max(0.0, 1.0 - len(issues) * 0.25)
    artifact_score = max(0.0, 1.0 - len(warnings) * 0.15)
    score = min(format_score, artifact_score)

    all_details = issues + [f"(경고) {w}" for w in warnings]

    return {
        "dimension": "korean_readability",
        "pass": len(issues) == 0 and len(warnings) == 0,
        "score": score,
        "auto_details": "; ".join(all_details) if all_details else "자동 검사 통과 (형식·번역체 기본 검사만)",
        "details": "; ".join(all_details) if all_details else "자동 검사 통과 (형식·번역체 기본 검사만)",
        "needs_human": True,
        "human_note": (
            "자동 검사는 형식과 일부 번역체만 탐지합니다. "
            "자연스러운 한국어인지, 어색한 조사/어미가 없는지, "
            "전문 용어가 적절한지는 사람이 확인해야 합니다."
        ),
        "auto_limitations": [
            "자연스러운 어순/조사 적절성 미검사",
            "전문 용어 번역 정확성 미검사",
            "문맥에 맞는 존댓말/반말 일관성 미검사",
        ],
    }


# ── 2. Factual fidelity ─────────────────────────────────────────────

def check_factual_fidelity(briefing: Dict[str, Any], source_item: Dict[str, Any]) -> Dict[str, Any]:
    """Automated surface checks + human evaluation sheet.

    MEASURES: numbers/proper nouns preserved from source, no date fabrication.
    CANNOT MEASURE: semantic accuracy, added claims, intent distortion.
    """
    auto_issues = []
    source_text = f"{source_item.get('title', '')} {source_item.get('summary', '')}"
    briefing_text = f"{briefing.get('display_title_ko', '')} {briefing.get('display_summary_ko', '')}"

    # Check if numbers from source are preserved in briefing
    source_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", source_text))
    briefing_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", briefing_text))
    # Numbers that appear in source but not in briefing (potential omission)
    # Numbers that appear in briefing but not in source (potential fabrication)
    fabricated_numbers = briefing_numbers - source_numbers
    # Filter out small numbers that could be artifacts (1, 2, etc.)
    fabricated_significant = {n for n in fabricated_numbers if len(n) > 1 or "%" in n}
    if fabricated_significant:
        auto_issues.append(f"원문에 없는 수치 등장: {', '.join(sorted(fabricated_significant)[:3])}")

    # Check proper noun preservation: extract capitalized words from English source
    if source_item.get("language") == "en":
        source_proper = set(re.findall(r"\b[A-Z][a-z]{2,}\b", source_text))
        source_proper -= {"The", "This", "That", "How", "What", "Why", "Every", "Show", "Ask"}
        briefing_proper = set(re.findall(r"\b[A-Z][a-z]{2,}\b", briefing_text))
        # Major proper nouns from source should appear in briefing
        missing_proper = source_proper - briefing_proper
        if len(source_proper) > 0 and len(missing_proper) > len(source_proper) * 0.7:
            auto_issues.append(f"주요 고유명사 다수 누락 ({len(missing_proper)}/{len(source_proper)})")

    auto_score = max(0.0, 1.0 - len(auto_issues) * 0.3)

    return {
        "dimension": "factual_fidelity",
        "pass": None if not auto_issues else False,
        "score": auto_score if auto_issues else None,
        "details": "; ".join(auto_issues) if auto_issues else "자동 표면 검사 이상 없음 (의미 정확성은 미검증)",
        "needs_human": True,
        "human_evaluation_sheet": {
            "1_fabricated_facts": "브리핑이 원문에 없는 사실을 생성했는가? [예/아니오/확인불가]",
            "2_exaggeration": "기능·성과·영향이 과장되었는가? [예/아니오/확인불가]",
            "3_date_errors": "날짜가 잘못되었는가? [예/아니오/해당없음]",
            "4_number_name_errors": "수치·고유명사에 오류가 있는가? [예/아니오/해당없음]",
            "5_fact_opinion_confusion": "사실과 해석이 혼동되었는가? [예/아니오/확인불가]",
            "overall_fidelity": "전체 충실도 [1-5점]",
        },
        "human_note": (
            "자동 검사는 수치·고유명사의 표면적 존재만 확인합니다. "
            "의미적 정확성, 과장, 사실/해석 혼동은 사람이 원문과 대조해야 합니다. "
            "미평가 항목은 '통과'로 계산하지 않습니다."
        ),
    }


# ── 3. Novelty detection ─────────────────────────────────────────────

_NOVELTY_CATEGORIES = {
    "first_release": "새 제품/프로젝트 최초 공개",
    "update": "기존 제품/프로젝트 새 업데이트",
    "discovery": "기존 자료 발견/재조명",
    "insufficient": "근거 부족으로 판단 불가",
}


def check_novelty_detection(briefing: Dict[str, Any], source_item: Dict[str, Any]) -> Dict[str, Any]:
    """Classify novelty type and check consistency with source metadata.

    Novelty taxonomy:
      - first_release: genuinely new product/project/announcement
      - update: new version/feature of existing product (still a NEW event)
      - discovery: existing material being surfaced/discussed
      - insufficient: cannot determine from available data

    IMPORTANT: 'update' IS a new event.  An update to an existing product
    is still newsworthy.  Only 'discovery' of known material is non-novel.
    """
    title = source_item.get("title", "")
    summary = source_item.get("summary", "")
    source_text = f"{title} {summary}".lower()
    expected = source_item.get("novelty", "")

    # Classify into taxonomy
    first_release_signals = ["최초", "첫 ", "새로 만든", "새롭게 개발", "신규", "brand new", "introduces"]
    update_signals = ["업데이트", "개정", "확대", "강화", "v2", "v3", "update", "upgrade", "release",
                      "출시", "공개", "발표", "시작", "launch", "announce", "발간"]
    discovery_signals = ["현황", "조사", "분석 보고", "survey", "state of", "토론", "경험 공유",
                         "왜 ", "이유", "stopped using", "best way to"]

    is_first = any(sig in source_text for sig in first_release_signals)
    is_update = any(sig in source_text for sig in update_signals)
    is_discovery = any(sig in source_text for sig in discovery_signals)

    if not title.strip():
        detected_type = "insufficient"
    elif is_first and not is_discovery:
        detected_type = "first_release"
    elif is_update and not is_discovery:
        detected_type = "update"
    elif is_discovery and not is_first:
        detected_type = "discovery"
    elif is_update and is_discovery:
        detected_type = "update"  # Updates take precedence
    else:
        detected_type = "insufficient"

    # Both first_release and update are "new events"
    detected_is_new = detected_type in ("first_release", "update")
    expected_is_new = expected == "new_event"

    # Data quality issue: empty title
    data_quality_issue = None
    if not title.strip():
        data_quality_issue = "빈 제목 — 신규성 판단 불가 (데이터 품질 문제)"

    if data_quality_issue:
        consistent = None  # Cannot evaluate
        score = None
    else:
        consistent = detected_is_new == expected_is_new
        score = 1.0 if consistent else 0.4

    return {
        "dimension": "novelty_detection",
        "pass": consistent,
        "score": score,
        "details": (
            f"예상={expected}, 분류={detected_type}({_NOVELTY_CATEGORIES[detected_type]})"
            + (f" | 데이터 문제: {data_quality_issue}" if data_quality_issue else "")
        ),
        "detected_type": detected_type,
        "needs_human": True,
        "human_note": (
            "자동 분류는 키워드 기반이며 맥락을 이해하지 못합니다. "
            "'기존 제품의 업데이트'는 새로운 사건입니다. "
            "브리핑이 사건의 성격을 정확히 전달하는지 사람이 확인해야 합니다."
        ),
    }


# ── 4. Date accuracy ─────────────────────────────────────────────────

def check_date_accuracy(briefing: Dict[str, Any], source_item: Dict[str, Any]) -> Dict[str, Any]:
    """Check date-related accuracy."""
    issues = []
    briefing_text = (briefing.get("display_summary_ko", "") + " " +
                     briefing.get("detail_summary_ko", ""))
    source_text = f"{source_item.get('title', '')} {source_item.get('summary', '')}"

    briefing_dates = set(re.findall(r"\d{4}년|\d{1,2}월 ?\d{1,2}일|\d{4}-\d{2}(?:-\d{2})?", briefing_text))
    source_dates = set(re.findall(r"\d{4}년|\d{1,2}월 ?\d{1,2}일|\d{4}-\d{2}(?:-\d{2})?", source_text))

    fabricated = briefing_dates - source_dates
    if fabricated:
        issues.append(f"원문에 없는 날짜: {', '.join(sorted(fabricated)[:3])}")

    # Check if published_at is missing
    if not source_item.get("published_at"):
        issues.append("발행일 누락 (데이터 품질 문제)")

    score = 1.0 if not issues else 0.5
    return {
        "dimension": "date_accuracy",
        "pass": len(issues) == 0,
        "score": score,
        "details": "; ".join(issues) if issues else "날짜 관련 문제 없음",
        "needs_human": False,
    }


# ── 5. Recommendation detail ─────────────────────────────────────────

def check_recommendation_detail(briefing: Dict[str, Any], source_item: Dict[str, Any]) -> Dict[str, Any]:
    """Check specificity of recommendation reason, why-it-matters, and action.

    MEASURES:
      - Whether recommendation uses a generic template vs article-specific content
      - Whether why_it_matters adds context beyond keyword echo
      - Whether action provides a concrete, distinct next step
    CANNOT MEASURE:
      - Whether the recommendation is actually useful to the user
      - Whether the connection to user goals is meaningful
    """
    issues = []
    reason = briefing.get("recommendation_reason_ko", "")
    why = briefing.get("why_it_matters_ko", "")
    action = briefing.get("recommended_action_ko", "")

    # --- recommendation_reason_ko ---
    if not reason:
        issues.append("추천 이유 누락")
    else:
        is_template = any(pat.match(reason) for pat in _RECOMMENDATION_TEMPLATES)
        if is_template:
            issues.append("추천 이유가 범용 템플릿과 동일 구조")

        # Check if reason mentions anything specific from the article
        source_title = source_item.get("title", "")
        source_proper_nouns = set(re.findall(r"[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)*", source_title))
        source_proper_nouns -= {"Show", "Ask", "Tell", "Launch", "Breaking", "Survey", "State"}
        source_ko_nouns = set(re.findall(r"[가-힣]{2,5}(?:전자|위원회|연구진|정통부)?", source_title))

        reason_mentions_article = any(
            noun.lower() in reason.lower() for noun in source_proper_nouns if len(noun) > 3
        ) or any(
            noun in reason for noun in source_ko_nouns if len(noun) >= 3
        )
        if not reason_mentions_article and not is_template:
            issues.append("추천 이유에 기사 고유 내용 미반영")

    # --- why_it_matters_ko ---
    if not why:
        issues.append("왜 중요한지 누락")
    else:
        is_why_template = any(pat.match(why) for pat in _WHY_MATTERS_TEMPLATES)
        if is_why_template:
            issues.append("'왜 중요한지'가 키워드 에코 템플릿과 동일")

    # --- recommended_action_ko ---
    if not action:
        issues.append("다음 행동 제안 누락")
    else:
        is_action_template = any(pat.match(action) for pat in _ACTION_TEMPLATES)
        if is_action_template:
            # Template actions are not necessarily wrong, but not specific
            issues.append("다음 행동이 범용 템플릿 사용")

    score = max(0.0, 1.0 - len(issues) * 0.2)
    return {
        "dimension": "recommendation_detail",
        "pass": len(issues) == 0,
        "score": score,
        "details": "; ".join(issues) if issues else "추천 내용이 기사별로 구체적",
        "needs_human": True,
        "human_note": (
            "자동 검사는 템플릿 패턴 반복 여부만 확인합니다. "
            "추천 이유가 (1) 기사의 구체적 대상을 언급하는지, "
            "(2) 사용자의 관심사/목표와 어떻게 연결되는지, "
            "(3) 그 연결에 원문 근거가 있는지는 사람이 확인해야 합니다."
        ),
    }


# ── 6. Repetition ────────────────────────────────────────────────────

def check_repetition(briefing: Dict[str, Any]) -> Dict[str, Any]:
    """Detect duplicated phrases within a single briefing."""
    issues = []
    title = briefing.get("display_title_ko", "")
    summary = briefing.get("display_summary_ko", "")
    fields = [title, summary,
              briefing.get("why_it_matters_ko", ""),
              briefing.get("recommendation_reason_ko", ""),
              briefing.get("recommended_action_ko", "")]

    all_text = " ".join(fields)
    words = all_text.split()

    # N-gram repetition (4-7 words)
    found_repeats = set()
    for n in range(4, min(8, len(words))):
        seen = set()
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i:i + n])
            if phrase in seen and len(phrase) > 15 and phrase not in found_repeats:
                found_repeats.add(phrase)
            seen.add(phrase)
    for phrase in sorted(found_repeats, key=len, reverse=True)[:3]:
        issues.append(f"반복 구문: '{phrase[:60]}'")

    # Title entirely in summary
    if title and summary and len(title) > 10 and title in summary:
        issues.append("제목이 요약에 그대로 포함됨")

    score = max(0.0, 1.0 - len(issues) * 0.25)
    return {
        "dimension": "repetition",
        "pass": len(issues) == 0,
        "score": score,
        "details": "; ".join(issues) if issues else "반복 표현 없음",
        "needs_human": False,
    }


# ── 7. Interest relevance ────────────────────────────────────────────

def check_interest_relevance(briefing: Dict[str, Any], source_item: Dict[str, Any]) -> Dict[str, Any]:
    """Check interest relevance using synonym-aware matching.

    MEASURES:
      - Whether keyword or its known synonyms appear in source content
      - Whether briefing content topically relates to the keyword domain
      - derived_from_ko consistency
    CANNOT MEASURE:
      - Deep semantic relevance (topic is related but keyword doesn't appear)
      - Whether the connection is meaningful for the user's specific goal
    """
    issues = []
    warnings = []
    keywords = source_item.get("matched_keywords", [])
    source_title = source_item.get("title", "").lower()
    source_summary = source_item.get("summary", "").lower()
    source_text = f"{source_title} {source_summary}"
    briefing_title = briefing.get("display_title_ko", "").lower()
    briefing_summary = briefing.get("display_summary_ko", "").lower()
    briefing_text = f"{briefing_title} {briefing_summary}"
    derived = briefing.get("derived_from_ko", "")

    if not keywords:
        issues.append("매칭 키워드 없음")
    else:
        # Check source content relevance (does source actually relate to keyword?)
        source_match_found = False
        briefing_match_found = False
        for kw in keywords:
            variants = _keyword_variants(kw)
            if any(v in source_text for v in variants):
                source_match_found = True
            if any(v in briefing_text for v in variants):
                briefing_match_found = True

        if not source_match_found:
            # Source itself doesn't mention the keyword — this is a matching quality issue,
            # not a briefing quality issue.  Flag but don't penalize briefing.
            warnings.append(f"원본 콘텐츠에 키워드 {keywords[:2]} 또는 동의어 미등장 (매칭 정확성 문제)")

        if not briefing_match_found and source_match_found:
            # Source has it but briefing lost it (translation issue)
            issues.append(f"원본에 있는 키워드가 브리핑에서 누락됨")

        # derived_from check
        if derived and keywords:
            if keywords[0] not in derived:
                # Check synonyms too
                variants = _keyword_variants(keywords[0])
                if not any(v in derived.lower() for v in variants):
                    warnings.append(f"derived_from '{derived}'이 첫 키워드 '{keywords[0]}'와 불일치")

    # Separate score for source-level and briefing-level
    score = max(0.0, 1.0 - len(issues) * 0.35 - len(warnings) * 0.1)
    all_details = issues + [f"(경고) {w}" for w in warnings]

    return {
        "dimension": "interest_relevance",
        "pass": len(issues) == 0,
        "score": score,
        "details": "; ".join(all_details) if all_details else "관심사 일치 (동의어 포함)",
        "needs_human": True,
        "human_note": (
            "키워드/동의어 일치는 표면적 확인입니다. "
            "실제로 그 관심사를 추적하는 사용자에게 유용한 내용인지, "
            "관심 주제와 사용자 목표·상황이 구별되어 반영되었는지는 사람이 판단해야 합니다."
        ),
    }


# ── Cross-briefing checks ────────────────────────────────────────────

def check_cross_briefing_repetition(briefings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Detect systemic template repetition across multiple briefings."""
    issues = []
    for field, label in [
        ("recommendation_reason_ko", "추천 이유"),
        ("why_it_matters_ko", "왜 중요한지"),
        ("recommended_action_ko", "다음 행동"),
    ]:
        values = [b.get(field, "") for b in briefings if b.get(field)]
        if len(values) < 3:
            continue
        unique = set(values)
        unique_ratio = len(unique) / len(values)

        if unique_ratio < 0.5:
            issues.append(
                f"{label}: {len(values)}건 중 고유값 {len(unique)}개 "
                f"({unique_ratio:.0%}) — 템플릿 반복 심각"
            )
        elif unique_ratio < 0.75:
            issues.append(
                f"{label}: {len(values)}건 중 고유값 {len(unique)}개 "
                f"({unique_ratio:.0%}) — 다양성 부족"
            )

    score = max(0.0, 1.0 - len(issues) * 0.3)
    return {
        "dimension": "cross_repetition",
        "pass": len(issues) == 0,
        "score": score,
        "details": "; ".join(issues) if issues else "브리핑 간 충분한 다양성",
        "needs_human": False,
    }


# ── Orchestrator ──────────────────────────────────────────────────────

def evaluate_single(briefing: Dict[str, Any], source_item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run all 7 evaluation dimensions on a single briefing."""
    return [
        check_korean_readability(briefing),
        check_factual_fidelity(briefing, source_item),
        check_novelty_detection(briefing, source_item),
        check_date_accuracy(briefing, source_item),
        check_recommendation_detail(briefing, source_item),
        check_repetition(briefing),
        check_interest_relevance(briefing, source_item),
    ]


def evaluate_batch(pairs: List[tuple], profiles: Optional[List[str]] = None) -> Dict[str, Any]:
    """Evaluate a batch of (briefing, source_item) pairs.

    Returns aggregate results.  Unevaluated items (score=None) are tracked
    separately and NEVER counted as successes.
    """
    results = []
    all_briefings = []

    for briefing, source_item in pairs:
        item_results = evaluate_single(briefing, source_item)
        results.append({
            "item_id": source_item.get("id", "unknown"),
            "title": source_item.get("title", "")[:60],
            "profile": source_item.get("eval_profile", "default"),
            "checks": item_results,
        })
        all_briefings.append(briefing)

    cross = check_cross_briefing_repetition(all_briefings)

    # Aggregate: separate evaluated from unevaluated
    dim_scores = {}
    dim_unevaluated = {}
    for result in results:
        for check in result["checks"]:
            dim = check["dimension"]
            if check["score"] is not None:
                dim_scores.setdefault(dim, []).append(check["score"])
            else:
                dim_unevaluated[dim] = dim_unevaluated.get(dim, 0) + 1

    summary = {}
    for dim, scores in dim_scores.items():
        summary[dim] = {
            "avg_score": sum(scores) / len(scores),
            "pass_rate": sum(1 for s in scores if s >= 0.8) / len(scores),
            "evaluated_count": len(scores),
            "unevaluated_count": dim_unevaluated.get(dim, 0),
        }
    # Add dimensions that are entirely unevaluated
    for dim, count in dim_unevaluated.items():
        if dim not in summary:
            summary[dim] = {
                "avg_score": None,
                "pass_rate": None,
                "evaluated_count": 0,
                "unevaluated_count": count,
            }

    return {
        "item_count": len(results),
        "profiles_used": sorted(set(r["profile"] for r in results)),
        "item_results": results,
        "cross_briefing": cross,
        "dimension_summary": summary,
        "evaluation_type_guide": {
            "fully_automated": ["date_accuracy", "repetition"],
            "auto_surface_plus_human": ["factual_fidelity", "korean_readability",
                                        "novelty_detection", "recommendation_detail",
                                        "interest_relevance"],
            "note": (
                "자동 테스트 통과는 표면적 형식 검증만 의미합니다. "
                "'auto_surface' 항목의 자동 점수가 높아도 의미적 품질은 미검증입니다. "
                "미평가 항목(score=None)은 통과 건수에 포함하지 않습니다."
            ),
        },
    }

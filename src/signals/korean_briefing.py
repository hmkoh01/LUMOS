from typing import Any, Dict, List
import re
from html import unescape

from src.signals.translation import translate_to_korean
from src.signals.content_briefing import make_content_briefing, extract_related_mentions


def build_korean_briefing(
    title: str,
    summary: str,
    source: str = "",
    category: str = "",
    matched_keywords: List[str] = None,
    role: str = "",
    action_hint: str = "",
    content_context: Dict[str, Any] = None,
) -> Dict[str, Any]:
    keywords = [str(item).strip() for item in (matched_keywords or []) if str(item).strip()]
    keyword_text = ", ".join(keywords[:3]) if keywords else "최근 관심사"
    topic = _topic_from(title, summary, keywords)
    clean_title = strip_post_format(clean_article_text(title))
    clean_summary = clean_article_text(summary)
    language = _guess_language(title, summary)

    if _guess_language(clean_title, "") == "en":
        # Headlines and summaries read in the user's own language so they can judge
        # relevance at a glance; if translation is unavailable, fall back to the
        # original English rather than blocking signal generation.
        display_title = translate_to_korean(clean_title) or clean_title or clean_summary[:120] or "제목 없는 소식"
    else:
        display_title = clean_title or clean_summary[:120] or "제목 없는 소식"
    display_title = polish_headline(strip_post_format(display_title))
    translated_summary = translate_to_korean(clean_summary) if clean_summary and _guess_language(clean_summary, "") == "en" else None
    display_summary = (translated_summary or clean_summary)[:500] or "설명이 제공되지 않아 제목까지만 확인할 수 있어요."
    detail = display_summary if clean_summary else ""
    limitation = ("수집된 제목과 짧은 설명을 정리했어요. 원문 전체나 영상 내용을 확인한 요약은 아니에요."
                  if clean_summary else "제목만 확보했어요. 구체적인 내용이나 결론은 원문에서 확인해주세요.")
    if _guess_language(display_title, "") == "en" or (clean_summary and _guess_language(display_summary, "") == "en"):
        limitation += " 한국어 번역을 확보하지 못한 부분은 원문으로 표시해요."

    context = content_context or {}
    content = {}
    headline_summary = ""
    if context.get("status") == "available":
        def translate(text):
            return translate_to_korean(text) if _guess_language(text, "") == "en" else text
        content = make_content_briefing(clean_title, clean_summary, context, translate)
        if content["headline"]:
            display_title = polish_headline(content["headline"])
            headline_summary = content.get("headline_summary", "")
        elif context.get("title"):
            display_title = polish_headline(translate(context["title"]) or context["title"])
        if content["translated_evidence"]:
            display_summary = content["translated_evidence"][0]
            detail = _compose_detail_paragraph(context.get("site_name", ""), content["translated_evidence"])
        limitation = ("게시글 작성자의 설명에서 핵심 내용을 골라 정리했어요. 작성자의 주장이나 계획을 독립적으로 검증한 것은 아니에요."
                      if context.get("basis") == "post_text" else
                      "원문 페이지에서 확보한 설명·본문 일부를 바탕으로 정리했어요. 영상·자막이나 페이지 밖의 자료는 확인하지 않았어요.")
        if any(_guess_language(part, "") == "en" for part in [display_title, *content.get("translated_evidence", [])]):
            limitation += " 번역을 확보하지 못한 부분은 원문으로 표시해요."

    exclude = {word.lower() for word in re.findall(r"[A-Za-z]+", clean_title)}
    if context.get("site_name"):
        exclude.add(context["site_name"].strip().lower())
    related_mentions = content.get("related_mentions") or extract_related_mentions(
        " ".join(filter(None, [clean_summary, context.get("description", ""), context.get("text", "")])), exclude)

    return {
        "briefing_version": 9,
        "content_context": context,
        "headline_evidence": content.get("headline_evidence", ""),
        "summary_evidence": content.get("evidence", []),
        "article_title": context.get("title", ""),
        "detail_summary_ko": detail,
        "detail_limitation_ko": limitation,
        "matched_keywords": keywords,
        "display_title_ko": display_title,
        "headline_summary_ko": headline_summary,
        "display_summary_ko": display_summary,
        "why_it_matters_ko": (
            f"관심사 {keyword_text}와 관련된 자료예요. 실제로 도움이 되는지는 제공된 설명과 원문을 확인해주세요."
        ),
        "recommendation_reason_ko": _recommendation_reason_ko(clean_title, clean_summary, topic),
        "derived_from_ko": f"'{keywords[0]}' 키워드에서 찾은 소식" if keywords else "",
        "recommended_action_ko": _next_read_ko(related_mentions, action_hint, topic),
        "original_title": title or "",
        "original_snippet": summary or "",
        "original_language": language,
    }


def _compose_detail_paragraph(site_name: str, sentences: List[str]) -> str:
    """Join extracted evidence into one readable paragraph with a topic lead-in,
    instead of a bare per-sentence bullet list that loses flow and context."""
    body = []
    for index, sentence in enumerate(sentences):
        if index == 0 or re.match(r"^(또한|그리고|이어서|하지만|반면)", sentence):
            body.append(sentence)
        else:
            body.append(f"또한, {sentence}")
    return " ".join(body)


def _recommendation_reason_ko(title: str, summary: str, topic: str) -> str:
    """Explain the article's trend signal, not merely the matching interest.

    The wording deliberately avoids attaching Korean particles to arbitrary
    keywords (for example, 'AI 인프라(가)'), which produces unnatural text.
    """
    text = f"{title} {summary}".casefold()
    if any(token in text for token in ("research", "study", "paper", "논문", "연구", "조사")):
        angle = "연구·조사 결과"
    elif any(token in text for token in ("launch", "release", "announce", "introduc", "update", "출시", "공개", "발표", "업데이트")):
        angle = "새 발표와 업데이트"
    elif any(token in text for token in ("case study", "case", "example", "사례", "도입", "적용")):
        angle = "실제 적용 사례"
    elif any(token in text for token in ("market", "funding", "growth", "시장", "투자", "성장", "매출")):
        angle = "시장 변화"
    else:
        angle = "최근 변화"
    return (
        f"{topic} 분야의 {angle}를 다뤄, 최근 흐름이 실제 적용이나 시장 변화로 "
        "어떻게 이어지는지 판단하는 데 도움이 될 만해 추천했어요."
    )


def clean_article_text(text: str) -> str:
    text = unescape(str(text or ""))
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
    return " ".join(re.sub(r"<[^>]*>", " ", text).split())


def strip_post_format(title: str) -> str:
    return re.sub(r"^(?:(?:Ask|Show|Tell|Launch)\s+HN\s*:\s*)+", "", title, flags=re.I).strip()


def polish_headline(title: str) -> str:
    # Narrow surface edits preserve the question and its scope; no inferred claims.
    title = re.sub(r"^(?:당신은|여러분은)\s+", "", title)
    title = re.sub(r"(?:합니까|하십니까)\?$", "하나요?", title)
    if len(title) > 52:
        cut = title.rfind(" ", 0, 53)
        title = (title[:cut] if cut >= 26 else title[:52]).rstrip(" ,:;-") + "…"
    return title.strip()


def _topic_from(title: str, summary: str, keywords: List[str]) -> str:
    text = " ".join([title or "", summary or ""]).lower()
    if keywords:
        mapped = _keyword_topic(keywords[0])
        if mapped:
            return mapped
    if "agent" in text:
        return "AI 에이전트"
    if "workflow" in text or "automation" in text:
        return "업무 자동화"
    if "github" in text or "repository" in text or "open source" in text:
        return "GitHub 트렌드"
    if "startup" in text or "product" in text:
        return "스타트업 제품"
    if "api" in text:
        return "API 생태계"
    return _compact_title(title) or "새로운 변화"


def _keyword_topic(keyword: str) -> str:
    raw = str(keyword or "").strip()
    lower = raw.lower()
    if "agent" in lower or "assistant" in lower:
        return "AI 에이전트"
    if "github" in lower or "repository" in lower:
        return "GitHub 트렌드"
    if "workflow" in lower or "automation" in lower or "자동화" in raw:
        return "업무 자동화"
    if "productivity" in lower or "생산성" in raw:
        return "생산성 툴"
    if "startup" in lower or "스타트업" in raw:
        return "스타트업 제품"
    if "rss" in lower or "blog" in lower or "블로그" in raw:
        return "공식 업데이트"
    return raw


def _next_read_ko(related_mentions: List[str], action_hint: str, topic: str) -> str:
    """Point to specific things this article actually names, instead of a
    templated line that repeats across every signal in the same topic bucket."""
    mentions = list(dict.fromkeys(m for m in (related_mentions or []) if m))[:3]
    if mentions:
        listed = ", ".join(mentions)
        return f"원문에 함께 언급된 {listed}도 이 소식과 어떻게 이어지는지 찾아보세요."
    return _action_ko(action_hint, topic)


def _action_ko(action_hint: str, topic: str) -> str:
    hint = (action_hint or "").lower()
    if "track" in hint or "compare" in hint:
        return f"비슷한 {topic} 사례를 2~3개 더 모아 흐름이 이어지는지 비교해보세요."
    if "review" in hint:
        return "원문을 빠르게 훑고 계속 추적할 만한 흐름인지 표시해보세요."
    if topic in {"AI 에이전트", "업무 자동화", "생산성 툴"}:
        return f"{topic}이 실제 업무나 제품 기능으로 이어지는 사례인지 확인해보세요."
    return f"{topic} 흐름을 계속 추적할지 원문을 보고 판단해보세요."


def _category_label(category: str) -> str:
    labels = {
        "AI_LLM_AGENT": "AI와 에이전트",
        "RESEARCH": "연구",
        "STARTUP_PRODUCT": "스타트업과 제품",
        "DEVELOPER_TECH": "개발자 도구",
        "COMPANY_TRACKING": "기업 변화",
        "CONTENT_SNS": "콘텐츠와 커뮤니티",
        "CAREER": "커리어",
        "DOMESTIC_INDUSTRY": "국내 산업",
        "workflow automation": "업무 자동화",
        "product strategy": "제품 전략",
        "startup experiments": "스타트업 실험",
    }
    return labels.get(category, category or "관심")


def _source_label(source: str) -> str:
    labels = {
        "mock": "샘플 데이터",
        "hackernews": "Hacker News",
        "github": "GitHub",
        "rss": "RSS",
        "official_ai_blogs": "공식 AI 블로그",
    }
    return labels.get(source, source or "선별 소스")


def _guess_language(title: str, summary: str) -> str:
    text = f"{title or ''} {summary or ''}"
    korean_chars = sum(1 for char in text if "\uac00" <= char <= "\ud7a3")
    ascii_letters = sum(1 for char in text if char.isascii() and char.isalpha())
    if korean_chars > 0 and korean_chars >= ascii_letters * 0.2:
        return "ko"
    if ascii_letters:
        return "en"
    return "unknown"


def _compact_title(title: str) -> str:
    clean = " ".join(str(title or "").split())
    if len(clean) <= 28:
        return clean
    return clean[:28].rstrip() + "..."

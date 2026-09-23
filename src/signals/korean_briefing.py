from typing import Any, Dict, List
import re
from html import unescape

from src.signals.translation import translate_to_korean


def build_korean_briefing(
    title: str,
    summary: str,
    source: str = "",
    category: str = "",
    matched_keywords: List[str] = None,
    role: str = "",
    action_hint: str = "",
) -> Dict[str, Any]:
    keywords = [str(item).strip() for item in (matched_keywords or []) if str(item).strip()]
    keyword_text = ", ".join(keywords[:3]) if keywords else "최근 관심사"
    topic = _topic_from(title, summary, keywords)
    category_text = _category_label(category)
    clean_title = clean_article_text(title)
    clean_summary = clean_article_text(summary)
    language = _guess_language(title, summary)

    if language == "en":
        # Headlines and summaries read in the user's own language so they can judge
        # relevance at a glance; if translation is unavailable, fall back to the
        # original English rather than blocking signal generation.
        display_title = translate_to_korean(clean_title) or clean_title or clean_summary[:120] or "제목 없는 소식"
        display_summary = (translate_to_korean(clean_summary) or clean_summary)[:500] or "제공된 요약이 없어요. 원문에서 내용을 확인해주세요."
    else:
        display_title = clean_title or clean_summary[:120] or "제목 없는 소식"
        display_summary = clean_summary[:500] or "제공된 요약이 없어요. 원문에서 내용을 확인해주세요."

    return {
        "briefing_version": 4,
        "matched_keywords": keywords,
        "display_title_ko": display_title,
        "display_summary_ko": display_summary,
        "why_it_matters_ko": (
            f"{category_text} 영역에서 이런 변화가 반복되면 제품 방향, 학습 우선순위, 추적할 경쟁 흐름이 달라질 수 있어요."
        ),
        "recommendation_reason_ko": (
            f"최근 추천 기준에 {keyword_text}이(가) 포함되어 있어 이 소식을 먼저 보여드려요."
        ),
        "derived_from_ko": f"'{keywords[0]}' 키워드에서 찾은 소식" if keywords else "",
        "recommended_action_ko": _action_ko(action_hint, topic),
        "original_title": title or "",
        "original_snippet": summary or "",
        "original_language": language,
    }


def clean_article_text(text: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", str(text or ""))).split())


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

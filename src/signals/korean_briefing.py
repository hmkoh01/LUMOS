from typing import Any, Dict, List


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
    source_text = _source_label(source)
    display_title = _display_title(topic, category_text)

    return {
        "display_title_ko": display_title,
        "display_summary_ko": (
            f"{topic} 흐름이 {source_text}에서 포착됐어요. "
            f"{_summary_angle(topic, source)} 오늘 확인할 변화만 짧게 추렸어요."
        ),
        "why_it_matters_ko": (
            f"{category_text} 영역에서 이런 변화가 반복되면 제품 방향, 학습 우선순위, 추적할 경쟁 흐름이 달라질 수 있어요."
        ),
        "recommendation_reason_ko": (
            f"최근 추천 기준에 {keyword_text}가 포함되어 있어 이 신호를 먼저 보여드려요."
        ),
        "recommended_action_ko": _action_ko(action_hint, topic),
        "original_title": title or "",
        "original_snippet": summary or "",
        "original_language": _guess_language(title, summary),
    }


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


def _display_title(topic: str, category_text: str) -> str:
    if topic in {"AI 에이전트", "업무 자동화"}:
        return f"{topic} 흐름이 실제 업무 적용 쪽으로 움직이고 있어요"
    if topic == "GitHub 트렌드":
        return "GitHub에서 볼 만한 구현 흐름이 감지됐어요"
    return f"{topic} 관련 신호를 확인해볼 만해요"


def _action_ko(action_hint: str, topic: str) -> str:
    hint = (action_hint or "").lower()
    if "track" in hint or "compare" in hint:
        return f"비슷한 {topic} 사례를 2~3개 더 모아 흐름이 이어지는지 비교해보세요."
    if "review" in hint:
        return "원문을 빠르게 훑고 계속 추적할 만한 흐름인지 표시해보세요."
    if topic in {"AI 에이전트", "업무 자동화", "생산성 툴"}:
        return f"{topic}이 실제 업무나 제품 기능으로 이어지는 사례인지 확인해보세요."
    return f"{topic} 흐름을 계속 추적할지 원문을 보고 판단해보세요."


def _summary_angle(topic: str, source: str) -> str:
    if source == "github":
        return "구현 사례나 저장소 움직임으로 이어지고 있는지 볼 만해요."
    if source == "hackernews":
        return "개발자 커뮤니티의 반응이 붙고 있는지 확인할 만해요."
    if source in {"rss", "official_ai_blogs"}:
        return "공식 발표나 제품 업데이트로 확인된 변화예요."
    if topic in {"AI 에이전트", "업무 자동화"}:
        return "단순한 아이디어보다 실제 사용 흐름에 가까운 변화예요."
    return "관심사와 이어질 수 있는 움직임이에요."


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

"""Presentation-only normalization for multilingual interest labels."""
from __future__ import annotations

_KOREAN_DISPLAY = {
    "ai agent development": "AI 에이전트 개발",
    "langgraph workflow": "LangGraph 워크플로",
    "execution interruption resume stability": "에이전트 실행 중단·재개 흐름",
}


def korean_display_interests(interests: list[str]) -> list[str]:
    """Improve known generic phrases without mutating stored user interests."""
    return [_KOREAN_DISPLAY.get(value.strip().casefold(), value.strip()) for value in interests if value.strip()]

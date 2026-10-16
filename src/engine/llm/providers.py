"""LLM provider interface and mock implementation.

Real providers (Gemini, etc.) implement ``LLMProvider``.  Tests inject
``MockLLMProvider`` which returns deterministic responses without any
network call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.engine.models import LLMTier


@dataclass
class LLMRequest:
    prompt: str = ""
    max_tokens: int = 1024
    temperature: float = 0.3
    tier: str = LLMTier.CHEAP


@dataclass
class LLMResponse:
    text: str = ""
    tokens_used: int = 0
    tier: str = LLMTier.CHEAP
    model: str = ""
    success: bool = True
    error: str = ""


class LLMProvider(ABC):
    """Abstract LLM provider."""

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a completion.  Must NOT make real API calls in test mode."""

    @abstractmethod
    def name(self) -> str:
        ...


class MockLLMProvider(LLMProvider):
    """Deterministic mock that returns canned Korean briefings.

    Useful for offline testing.  Tracks calls for assertion.
    """

    def __init__(self) -> None:
        self.calls: List[LLMRequest] = []
        self._response_override: Optional[str] = None

    def set_response(self, text: str) -> None:
        self._response_override = text

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        text = self._response_override or self._default_response(request)
        tokens = max(len(text) // 4, 10)
        return LLMResponse(
            text=text,
            tokens_used=tokens,
            tier=request.tier,
            model="mock",
            success=True,
        )

    def name(self) -> str:
        return "mock"

    @staticmethod
    def _default_response(request: LLMRequest) -> str:
        """Generate a plausible Korean briefing response.

        Detects batched prompts (multiple [N] items) and returns
        an array with one entry per item.
        """
        # Count items in the prompt to produce matching batch output
        item_count = request.prompt.count("[") // 2 or 1  # rough heuristic
        # More precise: count "[N]" patterns
        import re
        markers = re.findall(r"\[\d+\]", request.prompt)
        n = len(markers) if markers else 1

        if n == 1:
            return (
                '{"display_title_ko": "모의 한국어 제목",'
                ' "headline_summary_ko": "이것은 테스트용 한국어 요약입니다.",'
                ' "key_facts_ko": ["사실 1", "사실 2"]}'
            )
        import json
        items = []
        for i in range(n):
            items.append({
                "display_title_ko": f"모의 한국어 제목 {i+1}",
                "headline_summary_ko": f"이것은 테스트용 한국어 요약입니다. 항목 {i+1}번 설명.",
                "key_facts_ko": [f"사실 {i+1}-1", f"사실 {i+1}-2"],
            })
        return json.dumps(items, ensure_ascii=False)

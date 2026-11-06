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


class StructuredBriefingProvider(ABC):
    """Provider contract for source-grounded Engine v2 briefings.

    Unlike the legacy batch provider, this keeps the structured content result
    available for fact validation and per-user personalization.
    """

    @property
    @abstractmethod
    def cache_version(self) -> str:
        ...

    @abstractmethod
    def generate_content(self, candidate: Any) -> Dict[str, Any]:
        ...

    @abstractmethod
    def generate_personalization(
        self, content: Dict[str, Any], role: str, keywords: List[str], relevance: Dict[str, str],
    ) -> Dict[str, Any]:
        ...


class AgentPlatformEngineProvider(StructuredBriefingProvider):
    """Engine adapter for the existing Agent Platform structured client."""

    def __init__(self, config: Any, platform_config: Any = None, client_factory=None):
        self.config = config
        self._platform_config = platform_config
        self._client_factory = client_factory
        self.usage_events: List[Dict[str, Any]] = []

    @property
    def cache_version(self) -> str:
        from src.signals.llm_briefing import (
            BRIEFING_VALIDATOR_VERSION, CONTENT_PROMPT_VERSION, PERSONALIZATION_PROMPT_VERSION,
        )
        return ":".join((
            "agent-platform", self.config.llm.agent_platform_model,
            CONTENT_PROMPT_VERSION, PERSONALIZATION_PROMPT_VERSION, BRIEFING_VALIDATOR_VERSION,
        ))

    def _client(self):
        from src.engine.safety import check_external_call_allowed
        from src.signals.agent_platform import AgentPlatformConfig
        from src.signals.llm_briefing import AgentPlatformBriefingLLMClient
        check_external_call_allowed(self.config, call_description="Engine v2 Agent Platform briefing")
        platform = self._platform_config or AgentPlatformConfig.from_env()
        return AgentPlatformBriefingLLMClient(
            platform, self.config.llm.agent_platform_model,
            client_factory=self._client_factory, access_channel="engine_v2",
        )

    @staticmethod
    def _item(candidate: Any) -> Dict[str, Any]:
        return {
            "id": candidate.dedupe_key, "title": candidate.title, "summary": candidate.summary,
            "source": candidate.source, "url": candidate.url, "published_at": candidate.published_at,
        }

    def generate_content(self, candidate: Any) -> Dict[str, Any]:
        from src.signals.llm_briefing import generate_content_briefing
        response = generate_content_briefing(self._item(candidate), self._client(), use_cache=False)
        self._record_usage(response.get("metadata", {}))
        return response

    def generate_personalization(
        self, content: Dict[str, Any], role: str, keywords: List[str], relevance: Dict[str, str],
    ) -> Dict[str, Any]:
        from src.signals.llm_briefing import generate_personalized_reason
        response = generate_personalized_reason(content, role, keywords, self._client(), relevance=relevance)
        self._record_usage(response.get("metadata", {}))
        return response

    def _record_usage(self, metadata: Dict[str, Any]) -> None:
        self.usage_events.append({
            key: metadata.get(key) for key in (
                "call_type", "model", "model_version", "input_tokens", "output_tokens",
                "thinking_tokens", "latency_ms", "error_code", "finish_reason", "retries",
            )
        })


class MockStructuredBriefingProvider(StructuredBriefingProvider):
    """Offline-only structured provider for local Engine integration tests."""

    cache_version = "mock:content-v1:personal-v1"

    def generate_content(self, candidate: Any) -> Dict[str, Any]:
        return {"status": "success", "content_briefing": {
            "display_title_ko": candidate.title or "테스트 소식",
            "display_summary_ko": candidate.summary or "테스트용 원문 요약입니다.",
            "key_facts": [candidate.summary or candidate.title],
            "grounded_facts": [], "_validation": {"valid": True},
        }}

    def generate_personalization(
        self, content: Dict[str, Any], role: str, keywords: List[str], relevance: Dict[str, str],
    ) -> Dict[str, Any]:
        fact = (content.get("key_facts") or ["원문 변경"])[0]
        return {"status": "success", "personalization": {
            "source_facts_ko": fact, "user_relevance_ko": "테스트용 관련성 설명입니다.",
            "recommendation_reason_ko": f"{fact} {keywords[0] if keywords else '관심 분야'}와 연결해 확인할 수 있습니다.",
            "why_it_matters_ko": "원문 변경 범위를 비교할 수 있습니다.",
            "recommended_action_ko": "원문을 확인하세요.", "relevance_confidence": "medium",
            "_validation": {"valid": True},
        }}


def create_structured_provider(config: Any) -> StructuredBriefingProvider:
    """Select an offline mock or the explicit Agent Platform provider."""
    provider = config.llm.provider
    if provider == "mock":
        return MockStructuredBriefingProvider()
    if provider == "agent_platform":
        return AgentPlatformEngineProvider(config)
    raise ValueError(f"Unsupported Engine structured LLM provider: {provider}")


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

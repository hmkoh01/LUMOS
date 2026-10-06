"""
LLM provider abstraction for LUMOS Assistant.

Swap point: add OpenAIProvider / GeminiProvider by implementing LLMProvider.
Select via LUMOS_LLM_PROVIDER env var.

Environment variables:
  LUMOS_LLM_PROVIDER   anthropic | mock  (default: mock)
  ANTHROPIC_API_KEY    required when provider=anthropic
  LUMOS_LLM_MODEL      claude model id  (default: claude-haiku-4-5-20251001)
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Protocol, runtime_checkable

from src.assistant.retrieval import RetrievedContext

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMProvider(Protocol):
    def generate_answer(
        self,
        question: str,
        context_docs: List[RetrievedContext],
        history: List[Dict[str, str]],
    ) -> str: ...


class MockProvider:
    """Deterministic fallback for local dev / missing API key."""

    def generate_answer(
        self,
        question: str,
        context_docs: List[RetrievedContext],
        history: List[Dict[str, str]],
    ) -> str:
        if not context_docs:
            return (
                "[로컬 모드] 현재 기간에 관련 브리핑 소식이 없어요. "
                "먼저 오늘의 소식을 받아오면 질문할 수 있어요."
            )
        titles = [ctx.title for ctx in context_docs[:3] if ctx.title]
        lines = "\n".join(f"- {t}" for t in titles)
        return (
            f"[로컬 모드] {len(context_docs)}개의 관련 소식을 찾았어요:\n{lines}\n\n"
            "실제 AI 답변을 받으려면 LUMOS_LLM_PROVIDER=anthropic 과 "
            "ANTHROPIC_API_KEY 환경변수를 설정하세요."
        )


class ClaudeProvider:
    """Anthropic Claude — first production LLM provider."""

    _SYSTEM = (
        "당신은 LUMOS 뉴스 브리핑 어시스턴트입니다. "
        "아래 [참고 소식] 목록에 있는 내용만 사용해 답변하세요. "
        "목록에 없는 정보를 추측하거나 만들어내지 마세요. "
        "답변은 한국어로 간결하게 핵심만 전달하세요. "
        "출처 인용 번호([1], [2] 등)는 쓰지 마세요 — 서버가 출처를 따로 표시합니다."
    )

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic  # lazy import
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def generate_answer(
        self,
        question: str,
        context_docs: List[RetrievedContext],
        history: List[Dict[str, str]],
    ) -> str:
        context_block = self._build_context(context_docs)
        messages = list(history)
        messages.append({
            "role": "user",
            "content": f"{context_block}\n\n질문: {question}",
        })
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=self._SYSTEM,
                messages=messages,
            )
            return resp.content[0].text.strip()
        except Exception as exc:
            logger.error("Claude API error: %s", exc)
            raise

    @staticmethod
    def _build_context(docs: List[RetrievedContext]) -> str:
        if not docs:
            return "[참고 소식 없음]"
        lines = ["[참고 소식]"]
        for i, doc in enumerate(docs, 1):
            lines.append(f"{i}. {doc.title}")
            if doc.summary:
                lines.append(f"   요약: {doc.summary}")
            if doc.why_it_matters:
                lines.append(f"   중요한 이유: {doc.why_it_matters}")
            if doc.source_name:
                lines.append(f"   출처: {doc.source_name}")
        return "\n".join(lines)


def build_provider_from_env() -> LLMProvider:
    """
    Factory: reads LUMOS_LLM_PROVIDER to select provider.
    Falls back to MockProvider when API key is missing.

    Swap point: add elif branches for openai, gemini, etc.
    """
    name = os.environ.get("LUMOS_LLM_PROVIDER", "mock").strip().lower()

    if name == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            logger.warning(
                "LUMOS_LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY not set; "
                "falling back to MockProvider"
            )
            return MockProvider()
        model = os.environ.get("LUMOS_LLM_MODEL", "claude-haiku-4-5-20251001").strip()
        return ClaudeProvider(api_key=key, model=model)

    if name != "mock":
        logger.warning("Unknown LUMOS_LLM_PROVIDER=%r; using mock", name)

    return MockProvider()

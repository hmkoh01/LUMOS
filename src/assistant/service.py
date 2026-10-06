"""
AssistantService: orchestrates retrieval → LLM → conversation persistence.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from src.assistant.llm import LLMProvider, build_provider_from_env
from src.assistant.retrieval import RetrievalService, RetrievedContext, SQLiteRetrievalService

logger = logging.getLogger(__name__)

_CONTEXT_WINDOW = 6   # last N messages sent to LLM (= 3 conversation turns)


@dataclass
class Citation:
    signal_id: int
    title: str
    source_name: str
    url: str
    published_at: Optional[str]


@dataclass
class AssistantResponse:
    answer: str
    conversation_id: int
    message_id: int
    sources: List[Citation]


class AssistantService:
    def __init__(
        self,
        store,
        retrieval: Optional[RetrievalService] = None,
        llm: Optional[LLMProvider] = None,
    ) -> None:
        self._store = store
        self._retrieval: RetrievalService = retrieval or SQLiteRetrievalService(store)
        self._llm: LLMProvider = llm or build_provider_from_env()

    def chat(
        self,
        user_id: int,
        message: str,
        period: str = "week",
        selected_signal_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ) -> AssistantResponse:
        # Validate selected_signal_id ownership — silently ignore if not owned
        if selected_signal_id is not None:
            if not self._store.signal_belongs_to_user(selected_signal_id, user_id):
                selected_signal_id = None

        # Resolve conversation
        conversation_id = self._resolve_conversation(
            user_id, period, message, conversation_id
        )

        # Save user message
        self._store.add_conversation_message(
            conversation_id=conversation_id,
            role="user",
            content=message,
        )

        # Retrieve context from user's signals
        context_docs: List[RetrievedContext] = self._retrieval.retrieve(
            query=message,
            user_id=user_id,
            period=period,
            selected_signal_id=selected_signal_id,
            limit=5,
        )

        # Trimmed conversation history for LLM (excludes the message just saved)
        history = self._build_history(conversation_id, user_id)

        # Generate answer
        try:
            answer = self._llm.generate_answer(
                question=message,
                context_docs=context_docs,
                history=history,
            )
        except Exception as exc:
            logger.error("LLM generation failed: %s", exc)
            answer = "답변을 준비하지 못했어요. 잠시 후 다시 시도해 주세요."

        # Citations come from server-side retrieved docs — never from LLM output
        citations = [
            Citation(
                signal_id=ctx.signal_id,
                title=ctx.title,
                source_name=ctx.source_name,
                url=ctx.source_url,
                published_at=ctx.published_at,
            )
            for ctx in context_docs
        ]

        sources_json = json.dumps(
            [
                {
                    "signal_id": c.signal_id,
                    "title": c.title,
                    "source_name": c.source_name,
                    "url": c.url,
                    "published_at": c.published_at,
                }
                for c in citations
            ],
            ensure_ascii=False,
        )
        message_id = self._store.add_conversation_message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            sources_json=sources_json,
        )

        return AssistantResponse(
            answer=answer,
            conversation_id=conversation_id,
            message_id=message_id,
            sources=citations,
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _resolve_conversation(
        self,
        user_id: int,
        period: str,
        message: str,
        conversation_id: Optional[int],
    ) -> int:
        if conversation_id is None:
            return self._store.create_conversation(
                user_id=user_id, period=period, title=message[:80]
            )
        # Validate ownership
        conv = self._store.get_conversation(conversation_id, user_id)
        if conv is None:
            return self._store.create_conversation(
                user_id=user_id, period=period, title=message[:80]
            )
        return conversation_id

    def _build_history(
        self, conversation_id: int, user_id: int
    ) -> List[Dict[str, str]]:
        """Last _CONTEXT_WINDOW messages, excluding the just-saved user message."""
        msgs = self._store.get_conversation_messages(conversation_id, user_id)
        trimmed = msgs[:-1][-_CONTEXT_WINDOW:]
        return [{"role": m["role"], "content": m["content"]} for m in trimmed]

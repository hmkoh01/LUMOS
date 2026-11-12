"""Non-generative eligibility rules for readable briefing cards.

These checks run before a content briefing is requested.  They deliberately do
not rewrite a source into a more attractive story: a source that does not have
the information type the reader asked for simply does not become a card.
"""

from __future__ import annotations

from typing import Iterable, Tuple

from src.engine.models import RawCandidate


_AI_TREND_TERMS = (
    "ai trend", "ai trends", "ai industry", "artificial intelligence trend",
    "\uc778\uacf5\uc9c0\ub2a5 \ud2b8\ub80c\ub4dc", "ai \ud2b8\ub80c\ub4dc", "ai \uc0b0\uc5c5 \ub3d9\ud5a5",
)
_OPEN_SOURCE_TERMS = (
    "open source", "github", "developer tool", "development tool",
    "\uc624\ud508\uc18c\uc2a4", "\uac1c\ubc1c\uc790 \ub3c4\uad6c", "\uac1c\ubc1c \ub3c4\uad6c",
)

# ``AI 에이전트`` is a narrower request than general developer tooling.  A
# repository can be useful to developers and still provide no evidence that it
# concerns an agent's behaviour or a task an agent performs.  Keep this gate
# lexical and source-grounded: it is deliberately not a semantic/LLM guess.
_AI_AGENT_INTEREST_TERMS = (
    "ai agent", "ai agents", "agentic", "ai 에이전트", "에이전트 개발",
    "에이전트 워크플로", "에이전트 도구",
)
_AI_AGENT_EVIDENCE_TERMS = (
    "ai agent", "ai agents", "agentic", "agents", "agent", "에이전트", "mcp",
)
_AI_AGENT_FUNCTION_TERMS = (
    "context", "session", "memory", "workflow", "orchestrat", "mcp",
    "diagnos", "tool", "sdk", "voice", "multimodal", "prompt", "세션", "기억",
    "문맥", "작업 흐름", "도구", "진단", "음성",
)


def _asks_for_ai_agents(interest_text: str) -> bool:
    return any(term in interest_text for term in _AI_AGENT_INTEREST_TERMS)


def _has_explicit_agent_use_evidence(candidate: RawCandidate) -> bool:
    """Require both an agent reference and a source-described use/function.

    This accepts a source such as a session-memory or voice-agent framework,
    but rejects a generic Flutter/Cardano/developer-tools repository that was
    merely drawn into the same broad technical topic family.
    """
    source_text = " ".join((candidate.title or "", candidate.summary or "")).casefold()
    return (
        any(term in source_text for term in _AI_AGENT_EVIDENCE_TERMS)
        and any(term in source_text for term in _AI_AGENT_FUNCTION_TERMS)
    )


def _has_other_specific_interest_evidence(candidate: RawCandidate, interests: Iterable[str]) -> bool:
    """Do not suppress a separately explicit interest in a multi-interest profile."""
    source_text = " ".join((candidate.title or "", candidate.summary or "")).casefold()
    generic = {"ai", "agent", "agents", "agentic", "development", "developer", "tool", "tools", "workflow"}
    for interest in interests:
        normalized = str(interest or "").casefold().strip()
        if not normalized or _asks_for_ai_agents(normalized):
            continue
        tokens = [token for token in normalized.replace("/", " ").replace("-", " ").split()
                  if len(token) >= 3 and token not in generic]
        if any(token in source_text for token in tokens):
            return True
    return False


def card_information_type_eligible(candidate: RawCandidate, interests: Iterable[str]) -> Tuple[bool, str]:
    """Return whether a candidate can be phrased as the requested card type.

    GitHub repository search proves discoverability and recent repository
    activity, not an industry event.  It can support an open-source/developer
    tools card, but must not leak into an ``AI trend`` card merely because the
    repository mentions AI.
    """
    metrics = candidate.metrics or {}
    content_kind = str(metrics.get("content_kind") or "").lower()
    interest_text = " ".join(str(value or "").casefold() for value in interests)
    asks_ai_trend = any(term in interest_text for term in _AI_TREND_TERMS)
    asks_open_source = any(term in interest_text for term in _OPEN_SOURCE_TERMS)
    if (
        _asks_for_ai_agents(interest_text)
        and not _has_explicit_agent_use_evidence(candidate)
        and not _has_other_specific_interest_evidence(candidate, interests)
    ):
        return False, "AI-agent interest needs explicit agent function or use evidence"
    if content_kind == "repository_discovery" and asks_ai_trend and not asks_open_source:
        return False, "repository discovery is not an AI-trend news event"
    return True, "information type compatible"

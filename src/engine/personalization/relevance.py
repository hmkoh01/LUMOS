"""Evidence-based relevance tiers for a user's briefing feed."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List

from src.engine.models import RawCandidate


_GENERIC_INTEREST_WORDS = {
    "ai", "agent", "agents", "agentic", "workflow", "workflows", "tool", "tools",
    "development", "developer", "software",
}
_IMPORTANCE_TERMS = {
    "security", "vulnerability", "cve", "breaking", "compatibility", "deprecated",
    "requirement", "requires",
}
_TOPIC_FAMILIES = {
    "agentic_development": {
        "source": {"ai", "agent", "agents", "agentic", "codex", "llm", "mcp", "tool", "tools"},
        "interest": {"ai", "agent", "agents", "agentic", "codex", "llm", "coding", "developer", "development", "tool", "tools"},
    },
    "source_control": {
        "source": {"git", "repository", "repositories", "monorepo", "source control", "branch", "branches"},
        "interest": {"git", "repository", "repositories", "source control", "version control", "developer productivity"},
    },
    "workflow": {
        "source": {"workflow", "workflows", "interrupt", "resume", "orchestration"},
        "interest": {"workflow", "workflows", "langgraph", "interrupt", "resume", "orchestration"},
    },
}


@dataclass(frozen=True)
class RelevanceAssessment:
    level: str  # direct | topic | insufficient
    basis: str
    importance_signal: float = 0.0


def _text(candidate: RawCandidate) -> str:
    return " ".join((candidate.title or "", candidate.summary or "")).lower()


def _contains_term(text: str, term: str) -> bool:
    if term.isascii() and term.replace(" ", "").isalnum():
        return bool(re.search(rf"\b{re.escape(term)}\b", text))
    return term in text


def _specific_interest_terms(interests: Iterable[str]) -> List[str]:
    terms: List[str] = []
    for interest in interests:
        normalized = interest.strip().lower()
        if normalized:
            terms.append(normalized)
        for token in normalized.replace("/", " ").replace("-", " ").split():
            if len(token) >= 3 and token not in _GENERIC_INTEREST_WORDS:
                terms.append(token)
    return list(dict.fromkeys(terms))


def _shared_topic_family(source_text: str, interests: Iterable[str]) -> str | None:
    """Topic classification needs evidence from both the source and profile."""
    profile_text = " ".join(interests).lower()
    for family, terms in _TOPIC_FAMILIES.items():
        source_match = any(_contains_term(source_text, term) for term in terms["source"])
        profile_match = any(_contains_term(profile_text, term) for term in terms["interest"])
        if source_match and profile_match:
            return family
    return None


def assess_candidate_relevance(
    candidate: RawCandidate,
    user_interests: Iterable[str],
) -> RelevanceAssessment:
    """Classify a source/profile relation without inferring compatibility.

    ``direct`` requires an explicit, non-generic interest/product term in the
    source. ``topic`` requires a shared adjacent topic family. A merely
    AI-related source is insufficient for an unrelated user profile.
    """
    text = _text(candidate)
    interests = [interest for interest in user_interests if interest.strip()]
    importance_signal = 0.03 if any(term in text for term in _IMPORTANCE_TERMS) else 0.0
    if not interests:
        return RelevanceAssessment("topic", "no registered interests; discovery fallback", importance_signal)

    specific_terms = _specific_interest_terms(interests)
    matched_terms = [term for term in specific_terms if _contains_term(text, term)]
    matched_interest = any(
        interest.lower() in {value.lower() for value in candidate.matched_interests}
        for interest in interests
    )
    if matched_terms or matched_interest:
        return RelevanceAssessment(
            "direct", matched_terms[0] if matched_terms else "collector interest match", importance_signal,
        )

    topic_family = _shared_topic_family(text, interests)
    if topic_family:
        return RelevanceAssessment("topic", f"adjacent {topic_family.replace('_', ' ')} topic", importance_signal)
    return RelevanceAssessment("insufficient", "no source-grounded relationship to the user's interests", importance_signal)

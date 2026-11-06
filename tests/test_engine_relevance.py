from src.engine.models import RawCandidate, ScoredCandidate
from src.engine.personalization.ranker import get_reserve_candidates, personalise_rankings
from src.engine.personalization.relevance import assess_candidate_relevance


def _scored(key: str, title: str, summary: str = "", score: float = 0.5) -> ScoredCandidate:
    return ScoredCandidate(
        candidate=RawCandidate(dedupe_key=key, title=title, summary=summary),
        importance_score=score,
    )


def test_relevance_distinguishes_direct_topic_and_insufficient():
    interests = ["LangGraph workflow", "AI agent development"]
    assert assess_candidate_relevance(
        _scored("direct", "LangGraph 1.2.20 release").candidate, interests
    ).level == "direct"
    assert assess_candidate_relevance(
        _scored("topic", "Pydantic AI security update").candidate, interests
    ).level == "topic"
    assert assess_candidate_relevance(
        _scored("off-topic", "PostgreSQL vacuum documentation").candidate, interests
    ).level == "insufficient"


def test_short_ai_topic_term_does_not_match_inside_unrelated_word():
    interests = ["AI agent development"]
    assert assess_candidate_relevance(
        _scored("off-topic", "PostgreSQL vacuum guide", "database maintenance").candidate, interests
    ).level == "insufficient"


def test_personalised_ranking_excludes_insufficient_and_exposes_basis():
    interests = ["LangGraph workflow", "AI agent development"]
    cards = personalise_rankings([
        _scored("direct", "LangGraph interrupt IDs", score=0.70),
        _scored("topic", "MCP Python SDK compatibility change", score=0.69),
        _scored("off-topic", "PostgreSQL vacuum documentation", score=0.99),
    ], interests, set(), set(), {})
    assert [card["dedupe_key"] for card in cards] == ["direct", "topic"]
    assert cards[0]["relevance_level"] == "direct"
    assert cards[1]["relevance_level"] == "topic"
    assert cards[0]["relevance_basis"]


def test_importance_is_not_replaced_by_relevance_tier():
    interests = ["LangGraph workflow", "AI agent development"]
    cards = personalise_rankings([
        _scored("direct", "LangGraph minor documentation", score=0.25),
        _scored("topic", "MCP security compatibility change", score=0.90),
    ], interests, set(), set(), {})
    assert cards[0]["dedupe_key"] == "topic"


def test_reserves_do_not_backfill_insufficient_items_when_interests_known():
    reserves = get_reserve_candidates([
        _scored("topic", "MCP Python SDK update"),
        _scored("off-topic", "PostgreSQL vacuum documentation"),
    ], set(), set(), user_interests=["AI agent development"])
    assert [item.candidate.dedupe_key for item in reserves] == ["topic"]


def test_pando_interest_profiles_do_not_all_receive_the_same_tier():
    pando = _scored(
        "pando", "Scaling Git at OpenAI",
        "OpenAI built Pando, a Git-compatible backend for its monorepo as Codex increased concurrent work.",
    ).candidate
    assert assess_candidate_relevance(pando, ["AI coding agents and development infrastructure"]).level == "topic"
    assert assess_candidate_relevance(pando, ["Git repository operations and developer productivity"]).level == "direct"
    assert assess_candidate_relevance(pando, ["AI agent development"]).level == "topic"
    assert assess_candidate_relevance(pando, ["LangGraph workflow design"]).level == "insufficient"
    assert assess_candidate_relevance(pando, ["Korean cooking recipes"]).level == "insufficient"

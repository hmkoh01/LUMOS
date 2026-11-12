from src.engine.llm.handlers import _diverse_generation_candidates
from src.engine.models import RawCandidate, ScoredCandidate
from src.engine.personalization.ranker import personalise_rankings
from src.engine.collection.source_support import collection_support


def _scored(key, source, score):
    return ScoredCandidate(
        candidate=RawCandidate(dedupe_key=key, source=source, title="AI agent update", summary="AI agent update"),
        importance_score=score,
    )


def test_generation_keeps_a_competitive_second_source():
    items = [_scored("g1", "github", .80), _scored("g2", "github", .70), _scored("h1", "hackernews", .30)]
    selected = _diverse_generation_candidates(items, 3)
    assert {item.candidate.source for item in selected} == {"github", "hackernews"}


def test_generation_does_not_use_weak_source_as_filler():
    items = [_scored("g1", "github", .80), _scored("h1", "hackernews", .11)]
    selected = _diverse_generation_candidates(items, 2)
    assert [item.candidate.source for item in selected] == ["github"]


def test_display_keeps_competitive_source_alternative():
    items = [_scored("g1", "github", .80), _scored("g2", "github", .70), _scored("h1", "hackernews", .30)]
    cards = personalise_rankings(items, ["AI"], set(), set(), {}, display_limit=2)
    assert {card["candidate"].source for card in cards} == {"github", "hackernews"}


def test_domestic_stock_interest_is_not_sent_to_technology_collectors():
    support = collection_support("국내 주식 동향", ("github", "hackernews"))
    assert support["status"] == "awaiting_approved_source"
    assert support["sources"] == []

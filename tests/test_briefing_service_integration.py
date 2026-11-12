from src.engine.llm.briefing_adapter import experiment_item_to_engine_card
from datetime import date

from src.engine.config import EngineConfig
from src.engine.evaluation.scorer import evaluate_candidates
from src.engine.models import Period, RawCandidate, ScoredCandidate
from src.engine.personalization.ranker import get_reserve_candidates, personalise_rankings
from src.signals.card_presentation import prepare_card_title
from src.signals.llm_briefing_validator import validate_content_briefing


def _item():
    return {
        "id": "mcp-python-2.3.0",
        "content_status": "success",
        "display_title_ko": "MCP Python SDK v2.3.0: httpx2 요구 사항 추가 및 파라미터 처리 변경",
        "display_summary_ko": "httpx2 2.10 이상을 요구하고 등록 시 잘못된 도구 주석을 거부합니다.",
        "content_validation": {"valid": True, "checks": {"fact_grounding": {"details": [
            {"claim": "httpx2 2.10 이상을 요구합니다.", "quote_found": True, "meaning_supported": True},
        ]}}},
        "personalize_status": "success",
        "source_facts_ko": "MCP Python SDK v2.3.0은 httpx2 2.10 이상을 요구합니다.",
        "user_relevance_ko": "AI 에이전트 개발과 인접한 기술 주제입니다.",
        "recommendation_reason_ko": "MCP Python SDK의 httpx2 2.10 이상 요구 변경은 에이전트 도구 의존성을 점검할 때 확인할 항목입니다.",
        "why_it_matters_ko": "현재 환경의 의존성 범위를 비교할 수 있습니다.",
        "recommended_action_ko": "릴리스 노트의 요구 사항을 확인하세요.",
        "relevance_confidence": "medium",
        "relevance_level": "topic",
        "relevance_basis": "adjacent agent/developer tooling topic",
        "personalization_validation": {"valid": True},
    }


def test_long_title_is_a_two_line_presentation_not_a_fact_failure():
    title = "OpenAI Agents SDK v0.24.0, 세션 일괄 처리와 도구 실행 변경 사항을 포함한 상세 릴리스 안내"
    policy = prepare_card_title(title)
    assert policy.display_mode == "two_line"
    assert policy.text == title


def test_release_boilerplate_can_be_safely_removed_without_truncation():
    policy = prepare_card_title(
        "SDK v0.24.0 \ubc84\uc804 \ucd9c\uc2dc: \uc138\uc158 \uc77c\uad04 \ucc98\ub9ac \ucd94\uac00 \ubc0f \ub3c4\uad6c \uc2e4\ud589 \ubcc0\uacbd \uc0ac\ud56d\uacfc \ud638\ud658\uc131 \uc548\ub0b4 \uc0c1\uc138"
    )
    assert policy.text == "SDK v0.24.0, \uc138\uc158 \uc77c\uad04 \ucc98\ub9ac \ucd94\uac00 \ubc0f \ub3c4\uad6c \uc2e4\ud589 \ubcc0\uacbd \uc0ac\ud56d\uacfc \ud638\ud658\uc131 \uc548\ub0b4 \uc0c1\uc138"
    assert policy.shortened is True


def test_content_validator_keeps_grounded_long_title_for_two_line_display():
    source = {"title": "SDK v0.24.0", "summary": "Adds a session batch feature."}
    briefing = {
        "display_title_ko": "SDK v0.24.0, \uc138\uc158 \uc77c\uad04 \ucc98\ub9ac\uc640 \ub3c4\uad6c \uc2e4\ud589 \ubcc0\uacbd \uc0ac\ud56d\uc744 \ud3ec\ud568\ud55c \uc0c1\uc138 \ub9b4\ub9ac\uc2a4 \uc548\ub0b4\uc640 \uac80\ud1a0 \uc815\ubcf4",
        "display_summary_ko": "세션 일괄 처리 기능을 추가했습니다.",
        "content_type_label": "릴리스", "is_new_event": True, "key_entities": ["SDK"],
        "limitation_ko": "릴리스 노트만 확인했습니다.",
        "grounded_facts": [{"claim": "세션 일괄 처리를 추가했습니다.",
                            "source_quote": "Adds a session batch feature.", "type": "direct_fact"}],
    }
    validation = validate_content_briefing(briefing, source)
    assert validation["valid"] is True
    assert validation["checks"]["title_presentation"]["display_mode"] == "two_line"


def test_validated_experiment_result_reaches_engine_card_without_provider_call():
    imported = experiment_item_to_engine_card(_item())
    assert imported is not None
    assert imported["briefing"].display_title_ko.startswith("MCP Python SDK")
    assert imported["card_fields"]["relevance_level"] == "topic"
    cards = personalise_rankings(
        [ScoredCandidate(candidate=RawCandidate(
            dedupe_key="mcp-python-2.3.0", title="MCP Python SDK update", summary="httpx2 requirement",
        ), importance_score=0.8)],
        ["AI agent development"], set(), set(),
        {"mcp-python-2.3.0": imported["briefing"]},
        validated_card_fields={"mcp-python-2.3.0": imported["card_fields"]},
    )
    assert cards[0]["recommendation_reason_ko"] == imported["card_fields"]["recommendation_reason_ko"]
    assert cards[0]["recommended_action_ko"]


def test_fallback_reason_uses_validated_fact_and_topic_boundary():
    imported = experiment_item_to_engine_card(_item())
    cards = personalise_rankings(
        [ScoredCandidate(candidate=RawCandidate(
            dedupe_key="mcp-python-2.3.0", title="MCP Python SDK update", summary="httpx2 requirement",
        ), importance_score=0.8)],
        ["AI agent development"], set(), set(),
        {"mcp-python-2.3.0": imported["briefing"]},
    )
    assert "httpx2" in cards[0]["recommendation_reason_ko"]
    assert "비교·동향" in cards[0]["recommendation_reason_ko"]
    assert cards[0]["recommended_action_ko"] == "원문과 릴리스 노트를 확인하세요."


def test_production_ranking_never_revives_adjacent_topic_fallback_when_personalization_is_missing():
    """The legacy fallback was the source of the web's adjacent-topic copy."""
    imported = experiment_item_to_engine_card(_item())
    cards = personalise_rankings(
        [ScoredCandidate(candidate=RawCandidate(
            dedupe_key="mcp-python-2.3.0", title="MCP Python SDK update", summary="httpx2 requirement",
        ), importance_score=0.8)],
        ["AI agent development"], set(), set(),
        {"mcp-python-2.3.0": imported["briefing"]},
        require_validated_personalization=True,
    )
    assert cards == []


def test_period_scores_keep_independent_evaluation_and_safe_backfill():
    candidates = [
        RawCandidate(dedupe_key="direct", title="LangGraph workflow interrupt IDs", summary="strict resume mode", published_at="2026-11-07"),
        RawCandidate(dedupe_key="topic", title="MCP Python SDK dependency change", summary="httpx2 requirement", published_at="2026-11-07"),
        RawCandidate(dedupe_key="off-topic", title="PostgreSQL vacuum guide", summary="database maintenance", published_at="2026-11-07"),
    ]
    interests = ["LangGraph workflow", "AI agent development"]
    evaluated = {
        period: evaluate_candidates(candidates, period, interests, EngineConfig(), reference_date=date(2026, 11, 7))
        for period in (Period.DAILY, Period.WEEKLY, Period.MONTHLY)
    }
    assert all(items for items in evaluated.values())
    cards = personalise_rankings(evaluated[Period.DAILY], interests, set(), set(), {})
    assert [card["dedupe_key"] for card in cards] == ["direct", "topic"]
    reserves = get_reserve_candidates(
        evaluated[Period.DAILY], {"direct"}, set(), user_interests=interests,
    )
    assert [item.candidate.dedupe_key for item in reserves] == ["topic"]

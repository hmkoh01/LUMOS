from pathlib import Path
import threading

import pytest

from src.engine.config import EngineConfig
from src.engine.llm.cache import BriefingCache
from src.engine.llm.briefing_adapter import engine_card_to_display_payload
from src.engine.llm.providers import AgentPlatformEngineProvider, MockStructuredBriefingProvider, StructuredBriefingProvider, create_structured_provider
from src.engine.llm.service import EngineBriefingService
from src.engine.llm.structured_cache import StructuredBriefingCache
from src.engine.models import RawCandidate, ScoredCandidate
from src.engine.safety import ExternalCallBlocked


class FakeStructuredProvider(StructuredBriefingProvider):
    cache_version = "fake:model:content-v4:personal-v5:validator-v5"

    def __init__(self):
        self.content_calls = 0
        self.personal_calls = []

    def generate_content(self, candidate):
        self.content_calls += 1
        return {"status": "success", "metadata": {"model": "gemini-3.5-flash-lite", "input_tokens": 100, "output_tokens": 20, "thinking_tokens": 0}, "content_briefing": {
            "display_title_ko": f"{candidate.title} 핵심 변경",
            "display_summary_ko": "원문에 명시된 변경 사항을 요약합니다.",
            "key_facts": [f"{candidate.title}의 검증된 변경 사항"],
            "grounded_facts": [], "_validation": {"valid": True},
        }}

    def generate_personalization(self, content, role, keywords, relevance):
        self.personal_calls.append((tuple(keywords), relevance["level"]))
        return {"status": "success", "metadata": {"model": "gemini-3.5-flash-lite", "input_tokens": 50, "output_tokens": 10, "thinking_tokens": 0}, "personalization": {
            "source_facts_ko": content["key_facts"][0],
            "user_relevance_ko": "원문 범위 안에서 검토할 수 있습니다.",
            "recommendation_reason_ko": f"{content['key_facts'][0]} — {keywords[0]} 관점에서 확인할 수 있습니다.",
            "why_it_matters_ko": "원문에 명시된 변경 범위를 비교할 수 있습니다.",
            "recommended_action_ko": "원문을 확인하세요.",
            "relevance_confidence": "high",
            "_validation": {"valid": True},
        }}


def _service(tmp_path: Path):
    provider = FakeStructuredProvider()
    return EngineBriefingService(
        provider, BriefingCache(tmp_path / "briefings.sqlite"), StructuredBriefingCache(tmp_path / "structured.sqlite"),
    ), provider


def _scored():
    return [
        ScoredCandidate(candidate=RawCandidate(dedupe_key="langgraph", title="LangGraph workflow interrupt IDs", summary="strict resume"), importance_score=0.9),
        ScoredCandidate(candidate=RawCandidate(dedupe_key="mcp", title="MCP Python SDK update", summary="tool registration"), importance_score=0.8),
        ScoredCandidate(candidate=RawCandidate(dedupe_key="postgres", title="PostgreSQL vacuum", summary="database maintenance"), importance_score=0.99),
    ]


def test_shared_content_reused_and_personalization_is_profile_scoped(tmp_path):
    service, provider = _service(tmp_path)
    first = service.build_cards(_scored(), role="developer", interests=["LangGraph workflow", "AI agent development"],
                                ignored_keys=set(), tracked_keys=set())
    assert [card["dedupe_key"] for card in first] == ["langgraph", "mcp"]
    assert provider.content_calls == 2  # insufficient sources never consume content budget
    assert len(provider.personal_calls) == 2
    assert provider.personal_calls[0][0][0] == "LangGraph 워크플로"
    assert "AI 에이전트 개발" in provider.personal_calls[0][0]
    payload = engine_card_to_display_payload(first[0])
    assert payload["display_title_ko"]
    assert payload["recommendation_reason_ko"]

    second = service.build_cards(_scored(), role="developer", interests=["LangGraph workflow", "AI agent development"],
                                 ignored_keys=set(), tracked_keys=set())
    assert [card["dedupe_key"] for card in second] == ["langgraph", "mcp"]
    assert provider.content_calls == 2
    assert len(provider.personal_calls) == 2

    service.build_cards(_scored(), role="developer", interests=["LangGraph workflow", "AI agent development", "MCP tools"],
                        ignored_keys=set(), tracked_keys=set())
    assert provider.content_calls == 2
    assert len(provider.personal_calls) == 4


def test_invalid_content_never_becomes_a_card(tmp_path):
    service, provider = _service(tmp_path)

    def invalid(_candidate):
        provider.content_calls += 1
        return {
            "status": "validation_failed", "content_briefing": None,
            "metadata": {"validation_failed_checks": ["repository_presentation"]},
        }

    provider.generate_content = invalid
    cards = service.build_cards(_scored()[:1], role="developer", interests=["LangGraph workflow"],
                                ignored_keys=set(), tracked_keys=set())
    assert cards == []
    assert provider.personal_calls == []
    metrics = service.structured_cache.metric_summary()
    assert metrics["content_validation_rejected"] == 1
    assert metrics["content_validation_check_repository_presentation"] == 1
    assert "content_provider_or_transport_failed" not in metrics


def test_invalid_personalization_never_falls_back_to_a_generic_card(tmp_path):
    service, provider = _service(tmp_path)

    def invalid_personalization(*_args, **_kwargs):
        provider.personal_calls.append(("blocked", "topic"))
        return {"status": "validation_failed", "personalization": None}

    provider.generate_personalization = invalid_personalization
    cards = service.build_cards(
        _scored()[:2], role="developer",
        interests=["LangGraph workflow", "AI agent development"],
        ignored_keys=set(), tracked_keys=set(),
    )
    assert cards == []
    assert provider.content_calls == 2
    assert len(provider.personal_calls) == 2
    metrics = service.structured_cache.metric_summary()
    assert metrics["personalization_validation_rejected"] == 2


def test_generation_diagnostics_distinguish_validation_from_provider_failures(tmp_path):
    """Offline telemetry must preserve the failure class for operations."""
    service, provider = _service(tmp_path)
    diagnostics = {}

    def content_transport_failure(_candidate):
        provider.content_calls += 1
        return {"status": "failed", "metadata": {"error_code": "offline_fixture"}}

    provider.generate_content = content_transport_failure
    assert service.build_cards(
        _scored()[:1], role="developer", interests=["LangGraph workflow"],
        ignored_keys=set(), tracked_keys=set(), diagnostics=diagnostics,
    ) == []
    assert diagnostics == {
        "content_attempted": 1,
        "content_provider_or_transport_failed": 1,
        "cards_valid": 0,
    }

    # A separate service avoids a content-cache hit and proves the equivalent
    # classification for the profile-specific stage.
    nested = tmp_path / "personalization"
    nested.mkdir()
    service, provider = _service(nested)
    diagnostics = {}

    def personalization_transport_failure(*_args, **_kwargs):
        provider.personal_calls.append(("failed", "fixture"))
        return {"status": "failed", "metadata": {"error_code": "offline_fixture"}}

    provider.generate_personalization = personalization_transport_failure
    assert service.build_cards(
        _scored()[:1], role="developer", interests=["LangGraph workflow"],
        ignored_keys=set(), tracked_keys=set(), diagnostics=diagnostics,
    ) == []
    assert diagnostics["content_attempted"] == 1
    assert diagnostics["content_valid"] == 1
    assert diagnostics["personalization_attempted"] == 1
    assert diagnostics["personalization_provider_or_transport_failed"] == 1
    assert "personalization_validation_rejected" not in diagnostics


def test_five_valid_profile_specific_cards_keep_the_display_limit(tmp_path):
    service, _provider = _service(tmp_path)
    interests = ["AI agent development"]
    scored = [
        ScoredCandidate(
            candidate=RawCandidate(
                dedupe_key=f"valid-{index}", source="github",
                title=f"AI agent workflow change {index}", summary="source-confirmed tool change",
                matched_interests=interests,
            ),
            importance_score=1.0 - index * 0.05,
        )
        for index in range(5)
    ]
    cards = service.build_cards(
        scored, role="developer", interests=interests,
        ignored_keys=set(), tracked_keys=set(), display_limit=5,
    )
    assert len(cards) == 5
    assert all(card["recommendation_reason_ko"] for card in cards)


def test_ai_trend_does_not_spend_llm_budget_on_github_repository_discovery(tmp_path):
    service, provider = _service(tmp_path)
    cards = service.build_cards([
        ScoredCandidate(candidate=RawCandidate(
            dedupe_key="repo", source="github", title="owner/ai-project",
            summary="AI repository", metrics={"content_kind": "repository_discovery"},
        ), importance_score=0.9),
    ], role="reader", interests=["AI \ud2b8\ub80c\ub4dc"], ignored_keys=set(), tracked_keys=set())
    assert cards == []
    assert provider.content_calls == 0
    assert provider.personal_calls == []


def test_ai_agent_interest_does_not_spend_llm_budget_on_adjacent_developer_repositories(tmp_path):
    """Regression for the Flutter/Cardano cards that reached a broad agent topic."""
    service, provider = _service(tmp_path)
    cards = service.build_cards([
        ScoredCandidate(candidate=RawCandidate(
            dedupe_key="flutter-devtools", source="github", title="flutter/devtools",
            summary="A suite of performance and debugging tools for Flutter and Dart.",
            metrics={"content_kind": "repository_discovery"},
        ), importance_score=0.99),
        ScoredCandidate(candidate=RawCandidate(
            dedupe_key="claude-mem", source="github", title="thedotmack/claude-mem",
            summary="Persistent context across sessions for every agent; captures session memory for future tasks.",
            metrics={"content_kind": "repository_discovery"},
        ), importance_score=0.80),
    ], role="developer", interests=["AI 에이전트"], ignored_keys=set(), tracked_keys=set())
    assert [card["dedupe_key"] for card in cards] == ["claude-mem"]
    assert provider.content_calls == 1
    assert len(provider.personal_calls) == 1
    assert cards[0]["card_policy_versions"] == {
        "content_prompt": "v7", "personalization_prompt": "v8", "validator": "v8",
    }


def test_source_amendment_invalidates_shared_content_cache(tmp_path):
    service, provider = _service(tmp_path)
    original = [_scored()[0]]
    service.build_cards(original, role="developer", interests=["LangGraph workflow"], ignored_keys=set(), tracked_keys=set())
    amended = [_scored()[0]]
    amended[0].candidate.summary = "strict resume mode amended release notes"
    service.build_cards(amended, role="developer", interests=["LangGraph workflow"], ignored_keys=set(), tracked_keys=set())
    assert provider.content_calls == 2


def test_metrics_record_cache_and_card_outcomes_without_content(tmp_path):
    service, _provider = _service(tmp_path)
    service.build_cards(_scored(), role="developer", interests=["LangGraph workflow"], ignored_keys=set(), tracked_keys=set())
    metrics = service.structured_cache.metric_summary()
    assert metrics["content_cache_miss"] >= 1
    assert metrics["llm_content_requests"] >= 1
    assert metrics["cards_created"] >= 1
    assert metrics["llm_input_tokens"] > 0
    assert metrics["llm_estimated_cost_usd"] > 0


def test_agent_platform_provider_is_blocked_when_engine_is_off(monkeypatch):
    monkeypatch.setenv("LUMOS_BLOCK_EXTERNAL_CALLS", "true")
    config = EngineConfig(enabled=False, external_calls_allowed=False)
    provider = AgentPlatformEngineProvider(config)
    candidate = RawCandidate(dedupe_key="x", title="Release", summary="Summary")
    with pytest.raises(ExternalCallBlocked):
        provider.generate_content(candidate)


def test_provider_factory_defaults_to_offline_mock():
    assert isinstance(create_structured_provider(EngineConfig()), MockStructuredBriefingProvider)


def test_structured_cache_serializes_concurrent_worker_access(tmp_path):
    cache = StructuredBriefingCache(tmp_path / "structured.sqlite")
    errors = []

    def write_metric(index):
        try:
            cache.put_content(f"item-{index}", {"index": index})
            cache.record_metric("parallel_write")
            assert cache.get_content(f"item-{index}") == {"index": index}
        except Exception as exc:  # pragma: no cover - assertion preserves diagnostic
            errors.append(exc)

    threads = [threading.Thread(target=write_metric, args=(index,)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert cache.metric_summary()["parallel_write"] == 20

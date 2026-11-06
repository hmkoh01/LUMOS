from src.signals.llm_briefing_validator import (
    validate_content_briefing,
    validate_personalization,
)
from src.signals.llm_briefing import (
    _canonical_project_name, assess_relevance, generate_content_briefing, generate_personalized_reason,
)


LANGGRAPH_SOURCE = {
    "title": "langgraph==1.2.20",
    "summary": (
        "Release 1.2.20 adds a separate id for each interrupt in a task and a "
        "strict resume mode that refuses stale interrupt answers; it fixes the "
        "multiple-interrupts error so it links to the current documentation."
    ),
}

GROUNDING = [
    {"claim": "태스크 내 각 인터럽트에 별도 ID를 추가합니다.",
     "source_quote": "adds a separate id for each interrupt in a task", "type": "direct_fact"},
    {"claim": "오래된 인터럽트 답변을 거부하는 strict resume mode를 추가합니다.",
     "source_quote": "a strict resume mode that refuses stale interrupt answers", "type": "direct_fact"},
    {"claim": "multiple-interrupts 오류가 최신 문서를 가리키도록 수정합니다.",
     "source_quote": "fixes the multiple-interrupts error so it links to the current documentation", "type": "direct_fact"},
]


def _content_with(claim):
    return {
        "display_title_ko": "LangGraph 1.2.20, strict resume mode 추가",
        "display_summary_ko": "인터럽트 ID와 strict resume mode를 추가합니다.",
        "content_type_label": "프로젝트", "is_new_event": True,
        "key_entities": ["LangGraph"], "limitation_ko": "릴리스 요약만 확인했습니다.",
        "grounded_facts": [claim],
    }


def test_known_project_uses_official_display_casing():
    assert _canonical_project_name("langgraph==1.2.20") == "LangGraph"


def test_relevance_distinguishes_direct_topic_and_insufficient():
    assert assess_relevance(LANGGRAPH_SOURCE, ["LangGraph 기반 워크플로"])["level"] == "direct"
    assert assess_relevance({"title": "MCP Python SDK", "summary": "Tool protocol update"}, ["LangGraph"])["level"] == "topic"
    assert assess_relevance({"title": "Database driver", "summary": "SQL connection update"}, ["LangGraph"])["level"] == "insufficient"


def test_content_validator_rejects_unsupported_stability_effect():
    fact = {**GROUNDING[1], "claim": "strict resume mode가 실행 재개 안정성을 개선합니다."}
    result = validate_content_briefing(_content_with(fact), LANGGRAPH_SOURCE)
    assert result["valid"] is False
    assert result["checks"]["fact_grounding"]["details"][0]["meaning_supported"] is False


def test_content_validator_accepts_direct_release_fact():
    result = validate_content_briefing(_content_with(GROUNDING[2]), LANGGRAPH_SOURCE)
    assert result["valid"] is True
    assert result["checks"]["fact_grounding"]["details"][0]["meaning_supported"] is True


def test_content_validator_rejects_generic_release_title_when_change_exists():
    briefing = _content_with(GROUNDING[0])
    briefing["display_title_ko"] = "LangGraph 1.2.20 버전 출시"
    result = validate_content_briefing(briefing, LANGGRAPH_SOURCE)
    assert result["valid"] is False
    assert result["checks"]["title_change_specificity"]["pass"] is False


def test_content_validator_accepts_version_component_without_new_number():
    source = {"title": "SDK v0.24.0", "summary": "Adds a session batch feature."}
    briefing = _content_with({"claim": "세션 일괄 처리를 추가합니다.", "source_quote": "Adds a session batch feature", "type": "direct_fact"})
    briefing["display_title_ko"] = "SDK v0.24, 세션 일괄 처리 추가"
    result = validate_content_briefing(briefing, source)
    assert result["checks"]["number_fabrication"]["pass"] is True


def test_personalization_rejects_previous_unsupported_effect_claim():
    output = {
        "source_facts_ko": "태스크 내 인터럽트별 고유 ID와 strict resume mode가 추가됐습니다.",
        "user_relevance_ko": "중단과 재개 흐름을 검토할 때 참고할 수 있습니다.",
        "recommendation_reason_ko": (
            "요청하신 LangGraph 기반 워크플로와 AI 에이전트 개발에 직접 관련된 소식입니다. "
            "이 변경은 에이전트 실행 중단 및 재개 안정성을 직접적으로 개선합니다."
        ),
        "why_it_matters_ko": "워크플로 운영에 중요합니다.",
        "recommended_action_ko": "릴리스 노트를 확인하세요.",
        "relevance_confidence": "high",
    }
    result = validate_personalization(output, {"grounded_facts": GROUNDING})
    assert result["valid"] is False
    assert result["checks"]["effect_claim_fidelity"]["unsupported"] == ["stability"]
    assert result["checks"]["specific_context_first"]["pass"] is False


def test_personalization_rejects_unsupported_optimization_claim():
    output = {
        "source_facts_ko": "세션 쓰기를 API 제한 내에서 일괄 처리합니다.",
        "user_relevance_ko": "세션 처리 방식을 검토할 수 있습니다.",
        "recommendation_reason_ko": "세션 쓰기 일괄 처리는 대화 관리 구조를 최적화하는 데 활용할 수 있습니다.",
        "why_it_matters_ko": "세션 처리 변경점입니다.",
        "recommended_action_ko": "릴리스 노트를 확인하세요.",
        "relevance_confidence": "medium",
    }
    result = validate_personalization(output, {"grounded_facts": GROUNDING})
    assert result["valid"] is False
    assert result["checks"]["effect_claim_fidelity"]["unsupported"] == ["optimization"]


def test_personalization_rejects_unverified_upgrade_directive():
    output = {
        "source_facts_ko": "strict resume mode가 추가됐습니다.",
        "user_relevance_ko": "변경점을 검토할 수 있습니다.",
        "recommendation_reason_ko": "strict resume mode 변경을 검토할 만합니다.",
        "why_it_matters_ko": "재개 흐름의 변경점입니다.",
        "recommended_action_ko": "LangGraph를 업데이트하세요.",
        "relevance_confidence": "high",
    }
    result = validate_personalization(output, {"grounded_facts": GROUNDING})
    assert result["valid"] is False
    assert result["checks"]["no_unverified_deployment_directive"]["pass"] is False


def test_personalization_accepts_contextual_non_guarantee():
    output = {
        "source_facts_ko": "이번 릴리스는 태스크별 인터럽트 ID와 strict resume mode를 추가합니다.",
        "user_relevance_ko": "LangGraph 워크플로의 중단·재개 경로를 설계할 때 검토할 수 있는 변경입니다.",
        "recommendation_reason_ko": (
            "LangGraph 워크플로에서 인터럽트 답변을 식별하거나 재개 경로를 검토한다면, "
            "태스크별 ID와 strict resume mode 변경을 확인할 만합니다. "
            "원문은 이 변경의 안정성 결과를 언급하지 않습니다."
        ),
        "why_it_matters_ko": "중단된 작업을 다루는 흐름의 변경점을 검토하는 데 참고할 수 있습니다.",
        "recommended_action_ko": "릴리스 노트의 strict resume mode 설명을 확인하세요.",
        "relevance_confidence": "high",
    }
    result = validate_personalization(output, {"grounded_facts": GROUNDING})
    assert result["valid"] is True
    assert result["checks"]["effect_claim_fidelity"]["pass"] is True
    assert result["checks"]["specific_context_first"]["pass"] is True


def test_personalization_rejects_generic_topic_reason_without_source_anchor():
    output = {
        "source_facts_ko": "MCP Python SDK v2.3.0에 httpx2 2.10 이상 요구 사항이 추가되었습니다.",
        "user_relevance_ko": "AI 에이전트 개발과 인접한 기술 주제입니다.",
        "recommendation_reason_ko": "관련 도구의 변경 사항을 인접 주제 관점에서 검토할 만합니다.",
        "why_it_matters_ko": "의존성 변경을 확인할 수 있습니다.",
        "recommended_action_ko": "릴리스 노트를 확인하세요.",
        "relevance_confidence": "medium",
    }
    content = {"key_entities": ["MCP", "Python", "SDK", "httpx2"], "grounded_facts": []}
    result = validate_personalization(output, content)
    assert result["valid"] is False
    assert result["checks"]["source_detail_anchor"]["pass"] is False


def test_internal_case_study_cannot_be_labeled_a_public_release_without_evidence():
    source = {"title": "Scaling Git at OpenAI", "summary": "OpenAI describes Pando, a Git-compatible internal backend."}
    briefing = _content_with({"claim": "Pando is an internal Git-compatible backend.", "source_quote": "Pando", "type": "direct_fact"})
    briefing["display_title_ko"] = "Pando product release"
    result = validate_content_briefing(briefing, source)
    assert result["valid"] is False
    assert result["checks"]["availability_language"]["pass"] is False


def test_pando_topic_reason_uses_source_anchor_and_does_not_claim_adoption():
    class FakeClient:
        prompt = ""

        def generate_json(self, _system, prompt, **_kwargs):
            self.prompt = prompt
            return ({
                "source_facts_ko": "Pando is OpenAI's Git-compatible backend.",
                "user_relevance_ko": "Direct relevance to this profile is not confirmed.",
                "recommendation_reason_ko": "Pando shows an internal Git backend built around Codex-scale concurrent work; compare its source-control tradeoffs with your development infrastructure interests.",
                "why_it_matters_ko": "It is an internal case study, not a public product release.",
                "recommended_action_ko": "Review the article's Git compatibility and monorepo design choices.",
                "relevance_confidence": "medium",
            }, {"retries": 0})

    client = FakeClient()
    content = {
        "display_title_ko": "OpenAI introduces Pando", "display_summary_ko": "Internal Git backend case study.",
        "key_entities": ["Pando", "OpenAI", "Codex"],
        "grounded_facts": [{"claim": "Pando is a Git-compatible backend.", "source_quote": "Pando is a new backend for Git repositories", "type": "direct_fact"}],
    }
    result = generate_personalized_reason(content, "developer", ["AI coding agents"], client,
                                          relevance={"level": "topic", "basis": "adjacent agentic development topic"})
    assert result["status"] == "success"
    assert "SOURCE-ANCHOR CONTRACT" in client.prompt
    assert "Pando" in client.prompt


def test_generation_paths_block_invalid_effect_claims_without_retry():
    class FakeClient:
        _model = "fake"

        def generate_json(self, *args, **kwargs):
            return ({
                "display_title_ko": "LangGraph 1.2.20 출시",
                "display_summary_ko": "strict resume mode가 안정성을 개선합니다.",
                "content_type_label": "프로젝트", "is_new_event": True,
                "key_entities": ["LangGraph"], "limitation_ko": "릴리스 요약입니다.",
                "grounded_facts": [{**GROUNDING[1], "claim": "strict resume mode가 안정성을 개선합니다."}],
            }, {"retries": 0})

    result = generate_content_briefing(LANGGRAPH_SOURCE, FakeClient(), use_cache=False)
    assert result["status"] == "validation_failed"


def test_personalization_blocks_missing_required_field_without_retry():
    class FakeClient:
        def generate_json(self, *args, **kwargs):
            return ({
                "source_facts_ko": "strict resume mode가 추가됐습니다.",
                "recommendation_reason_ko": "재개 경로를 검토할 만합니다.",
                "why_it_matters_ko": "흐름 변경점입니다.",
                "recommended_action_ko": "릴리스 노트를 확인하세요.",
                "relevance_confidence": "high",
            }, {"retries": 0})

    result = generate_personalized_reason(
        {"grounded_facts": GROUNDING}, "개발자", ["LangGraph"], FakeClient(),
    )
    assert result["status"] == "validation_failed"

    class FakePersonalizationClient:
        def generate_json(self, *args, **kwargs):
            return ({
                "source_facts_ko": "strict resume mode가 추가됐습니다.",
                "user_relevance_ko": "재개 경로를 검토할 수 있습니다.",
                "recommendation_reason_ko": "이 변경은 안정성을 직접적으로 개선합니다.",
                "why_it_matters_ko": "운영 안정성이 향상됩니다.",
                "recommended_action_ko": "릴리스 노트를 확인하세요.",
                "relevance_confidence": "high",
            }, {"retries": 0})

    result = generate_personalized_reason(
        {"grounded_facts": GROUNDING}, "개발자", ["LangGraph"], FakePersonalizationClient(),
    )
    assert result["status"] == "validation_failed"

from src.engine.llm.card_quality import card_information_type_eligible
from src.engine.models import RawCandidate
from src.signals.llm_briefing import generate_content_briefing
from src.signals.llm_briefing_validator import validate_content_briefing, validate_personalization


def _content(*, title, summary, fact, kind=""):
    return {
        "display_title_ko": title,
        "display_summary_ko": summary,
        "content_type_label": "test",
        "is_new_event": False,
        "key_entities": ["\uc8fc\ucd5c \uae30\uad00"],
        "limitation_ko": "\uc6d0\ubb38 \uc694\uc57d\uc5d0\uc11c \ud655\uc778\ud55c \uc815\ubcf4\ub9cc \ud3ec\ud568\ud569\ub2c8\ub2e4.",
        "grounded_facts": [fact],
    }


def test_ai_trend_rejects_repository_discovery_before_llm():
    candidate = RawCandidate(
        dedupe_key="repo", source="github", title="owner/agent-tool", summary="An AI agent toolkit.",
        metrics={"content_kind": "repository_discovery"},
    )
    assert card_information_type_eligible(candidate, ["AI \ud2b8\ub80c\ub4dc"]) == (
        False, "repository discovery is not an AI-trend news event",
    )
    assert card_information_type_eligible(candidate, ["AI \uc624\ud508\uc18c\uc2a4"]) == (True, "information type compatible")


def test_ai_agent_interest_requires_source_described_agent_function_not_generic_dev_tools():
    flutter = RawCandidate(
        dedupe_key="flutter-devtools", source="github", title="flutter/devtools",
        summary="A suite of performance and debugging tools for Flutter and Dart.",
        metrics={"content_kind": "repository_discovery"},
    )
    cardano = RawCandidate(
        dedupe_key="cardano-portal", source="github", title="cardano-foundation/developer-portal",
        summary="Developer resources, documentation, APIs and SDKs for Cardano.",
        metrics={"content_kind": "repository_discovery"},
    )
    agent_memory = RawCandidate(
        dedupe_key="claude-mem", source="github", title="thedotmack/claude-mem",
        summary="Persistent context across sessions for every agent; captures session memory for future tasks.",
        metrics={"content_kind": "repository_discovery"},
    )
    for candidate in (flutter, cardano):
        allowed, reason = card_information_type_eligible(candidate, ["AI 에이전트"])
        assert allowed is False
        assert reason == "AI-agent interest needs explicit agent function or use evidence"
    assert card_information_type_eligible(agent_memory, ["AI 에이전트"])[0] is True


def test_repository_title_cannot_lead_with_repository_name_or_generic_introduction():
    source = {
        "title": "owner/agent-tool", "summary": "Repository for an AI agent toolkit.",
        "content_kind": "repository_discovery",
    }
    result = validate_content_briefing(_content(
        title="owner/agent-tool \uc18c\uac1c",
        summary="AI \uc5d0\uc774\uc804\ud2b8 \ub3c4\uad6c \uc800\uc7a5\uc18c\ub97c \uc18c\uac1c\ud569\ub2c8\ub2e4.",
        fact={"claim": "AI \uc5d0\uc774\uc804\ud2b8 \ub3c4\uad6c\uc6a9 \uc800\uc7a5\uc18c\uc785\ub2c8\ub2e4.", "source_quote": "AI agent toolkit", "type": "direct_fact"},
    ), source)
    assert result["valid"] is False
    assert result["checks"]["repository_presentation"]["pass"] is False


def test_repository_discovery_wording_and_adjacent_reason_are_rejected():
    source = {
        "source": "github", "title": "flutter/devtools",
        "summary": "Performance and debugging tools for Flutter and Dart.",
        "content_kind": "repository_discovery",
    }
    content = _content(
        title="Flutter 및 Dart용 개발자 도구 저장소 발견",
        summary="Flutter와 Dart 앱의 실행 상태를 살피는 도구 모음입니다.",
        fact={"claim": "개발자 도구 모음입니다.", "source_quote": "debugging tools", "type": "direct_fact"},
        kind="repository_discovery",
    )
    assert validate_content_briefing(content, source)["valid"] is False
    personalization = {
        "source_facts_ko": "개발자 도구 모음입니다.",
        "user_relevance_ko": "AI 에이전트 관심사와 직접 연결되지 않습니다.",
        "recommendation_reason_ko": "직접적 관련성이 낮지만 프로젝트 저장소 구조를 검토할 수 있습니다.",
        "why_it_matters_ko": "도구 구성을 확인할 수 있습니다.",
        "recommended_action_ko": "원문을 확인하세요.",
        "relevance_confidence": "low",
    }
    result = validate_personalization(personalization, content, registered_interests=["AI 에이전트"])
    assert result["valid"] is False
    assert result["checks"]["not_boilerplate"]["generic_personalization"] is True


def test_cross_domain_fixtures_accept_event_first_cards_with_grounded_summaries():
    fixtures = [
        ("\uc2e0\uc785 \uac1c\ubc1c\uc790 \ucc44\uc6a9 \uc811\uc218 \uc2dc\uc791", "\uc8fc\ucd5c \uae30\uad00\uc774 \uc2e0\uc785 \uac1c\ubc1c\uc790 \ucc44\uc6a9\uc758 \uc811\uc218 \uc2dc\uc791\uc77c\uc744 \uc548\ub0b4\ud588\uc2b5\ub2c8\ub2e4.", "\ucc44\uc6a9 \uc811\uc218\uc640 \ub9c8\uac10\uc77c\uc744 \uacf5\uace0\ud588\uc2b5\ub2c8\ub2e4."),
        ("\uae30\uc900\uae08\ub9ac \uacb0\uc815 \ub0b4\uc6a9 \ubc1c\ud45c", "\uae30\uad00\uc774 \uae30\uc900\uae08\ub9ac \uacb0\uc815 \ub0b4\uc6a9\uc744 \ubc1c\ud45c\ud588\uc2b5\ub2c8\ub2e4.", "\uae30\uc900\uae08\ub9ac \uacb0\uc815 \ub0b4\uc6a9\uc744 \ubc1c\ud45c\ud588\uc2b5\ub2c8\ub2e4."),
        ("\uc0c8 \uc815\ubd80 R&D \uc9c0\uc6d0\uc0ac\uc5c5 \uacf5\ubaa8 \uc548\ub0b4", "\uc8fc\ucd5c \uae30\uad00\uc774 \uc9c0\uc6d0 \ub300\uc0c1\uacfc \uc811\uc218 \uae30\uac04\uc744 \uacf5\uace0\ud588\uc2b5\ub2c8\ub2e4.", "\uc9c0\uc6d0 \ub300\uc0c1\uacfc \uc811\uc218 \uae30\uac04\uc744 \uacf5\uace0\ud588\uc2b5\ub2c8\ub2e4."),
        ("\uc5b8\uc5b4 \ubaa8\ub378 \ud559\uc2b5 \ubc29\ubc95\uc744 \ub2e4\ub8ec \uc0c8 \uc5f0\uad6c \ubc1c\ud45c", "\uc800\uc790\ub4e4\uc774 \uc5b8\uc5b4 \ubaa8\ub378\uc758 \ud559\uc2b5 \ubc29\ubc95\uc744 \ub2e4\ub8ec \ub17c\ubb38\uc744 \ubc1c\ud45c\ud588\uc2b5\ub2c8\ub2e4.", "\uc5b8\uc5b4 \ubaa8\ub378\uc758 \ud559\uc2b5 \ubc29\ubc95\uc744 \ub2e4\ub8ec \ub17c\ubb38\uc744 \ubc1c\ud45c\ud588\uc2b5\ub2c8\ub2e4."),
        ("\uc9c0\uc5ed \ubb38\ud654\ud589\uc0ac \uc77c\uc815 \uacf5\uac1c", "\uc8fc\ucd5c \uae30\uad00\uc774 \ud589\uc0ac \uae30\uac04\uacfc \uc7a5\uc18c\ub97c \uc548\ub0b4\ud588\uc2b5\ub2c8\ub2e4.", "\ud589\uc0ac \uae30\uac04\uacfc \uc7a5\uc18c\ub97c \uc548\ub0b4\ud588\uc2b5\ub2c8\ub2e4."),
    ]
    for title, summary, quote in fixtures:
        source = {"title": "\uacf5\uc2dd \uc6d0\ubb38", "summary": quote, "content_kind": "official_update"}
        result = validate_content_briefing(_content(
            title=title, summary=summary,
            fact={"claim": quote, "source_quote": quote, "type": "direct_fact"},
        ), source)
        assert result["valid"], result


def test_personalization_requires_an_interest_specific_reason_when_interest_is_available():
    content = {"key_entities": ["\uc8fc\ucd5c \uae30\uad00"], "grounded_facts": []}
    personalization = {
        "source_facts_ko": "\uc2e0\uc785 \uac1c\ubc1c\uc790 \ucc44\uc6a9 \uc811\uc218\uc640 \ub9c8\uac10\uc77c\uc744 \uacf5\uace0\ud588\uc2b5\ub2c8\ub2e4.",
        "user_relevance_ko": "\uad00\ub828 \ubd84\uc57c\uc5d0\uc11c \uc0b4\ud3b4\ubd24\uc2b5\ub2c8\ub2e4.",
        "recommendation_reason_ko": "\uc8fc\ucd5c \uae30\uad00\uc758 \uacf5\uace0\ub97c \ud655\uc778\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.",
        "why_it_matters_ko": "\uc6d0\ubb38\uc5d0 \uc811\uc218 \uae30\uac04\uc774 \uc788\uc2b5\ub2c8\ub2e4.",
        "recommended_action_ko": "\uc6d0\ubb38\uc5d0\uc11c \uc9c0\uc6d0 \uc870\uac74\uc744 \ud655\uc778\ud558\uc138\uc694.",
        "relevance_confidence": "medium",
    }
    result = validate_personalization(personalization, content, registered_interests=["\uc2e0\uc785 \uac1c\ubc1c\uc790 \ucc44\uc6a9"])
    assert result["valid"] is False
    assert result["checks"]["interest_specificity"]["pass"] is False


def test_content_prompt_requires_event_first_and_source_type_specific_copy():
    class FakeClient:
        _model = "fixture"
        system = ""

        def generate_json(self, system, _prompt, **_kwargs):
            self.system = system
            return ({
                "display_title_ko": "\ucc44\uc6a9 \uc811\uc218 \uc2dc\uc791 \uc548\ub0b4",
                "display_summary_ko": "\uc8fc\ucd5c \uae30\uad00\uc774 \uc811\uc218 \uae30\uac04\uacfc \uc9c0\uc6d0 \uc790\uaca9\uc744 \uacf5\uace0\ud588\uc2b5\ub2c8\ub2e4.",
                "content_type_label": "job", "is_new_event": True,
                "key_entities": ["\uc8fc\ucd5c \uae30\uad00"], "key_numbers": [],
                "information_gaps": "\uc138\ubd80 \uc804\ud615 \uc77c\uc815\uc740 \uc6d0\ubb38 \ud655\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4.",
                "limitation_ko": "\uacf5\uace0 \uc694\uc57d\uc5d0 \uc788\ub294 \uc815\ubcf4\ub9cc \ub2e4\ub8f9\ub2c8\ub2e4.",
                "grounded_facts": [{
                    "claim": "\uc811\uc218 \uae30\uac04\uacfc \uc9c0\uc6d0 \uc790\uaca9\uc744 \uacf5\uace0\ud588\uc2b5\ub2c8\ub2e4.",
                    "source_quote": "application period and eligibility", "type": "direct_fact",
                }],
            }, {"retries": 0})

    client = FakeClient()
    result = generate_content_briefing({
        "source": "fixture", "title": "Official hiring notice",
        "summary": "application period and eligibility", "content_kind": "job_announcement",
    }, client, use_cache=False)
    assert result["status"] == "success"
    assert "CARD QUALITY POLICY" in client.system
    assert "repository-discovery" in client.system

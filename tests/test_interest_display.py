from src.engine.personalization.interest_display import korean_display_interests


def test_known_english_interest_has_korean_display_without_mutation():
    raw = ["AI agent development", "LangGraph workflow", "MCP Python SDK"]
    assert korean_display_interests(raw) == ["AI 에이전트 개발", "LangGraph 워크플로", "MCP Python SDK"]
    assert raw[0] == "AI agent development"


def test_korean_and_proper_names_are_preserved():
    assert korean_display_interests(["에이전트 개발", "Pydantic AI", "MCP"] ) == ["에이전트 개발", "Pydantic AI", "MCP"]

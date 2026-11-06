"""Offline checks for the isolated Agent Platform configuration."""
import os

import pytest

from src.signals.agent_platform import AgentPlatformConfig, AgentPlatformConfigurationError
from src.signals.llm_briefing import AgentPlatformBriefingLLMClient
from tools import gemini_briefing_experiment as experiment


def _enterprise_env():
    return {
        "GOOGLE_GENAI_USE_ENTERPRISE": "true",
        "GOOGLE_API_KEY": "agent-platform-test-key",
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_LOCATION": "global",
    }


def test_agent_platform_factory_uses_enterprise_and_never_developer_key(monkeypatch):
    monkeypatch.setattr(os, "environ", {**os.environ, **_enterprise_env(), "GEMINI_API_KEY": "developer-key"})
    config = AgentPlatformConfig.from_env()
    captured = {}

    def fake_factory(**kwargs):
        captured.update(kwargs)
        return object()

    config.create_client(fake_factory)
    assert captured == {
        "enterprise": True, "api_key": "agent-platform-test-key",
        "project": "test-project", "location": "global",
        "retry_attempts": 1, "api_version": "v1",
    }
    assert "developer-key" not in repr(captured)


def test_missing_enterprise_setting_fails_without_fallback(monkeypatch):
    monkeypatch.setattr(os, "environ", {"GEMINI_API_KEY": "developer-key"})
    with pytest.raises(AgentPlatformConfigurationError):
        AgentPlatformConfig.from_env()


def test_current_sdk_is_rejected_before_any_client_is_created(monkeypatch):
    monkeypatch.setattr(os, "environ", _enterprise_env())
    monkeypatch.setattr("importlib.metadata.version", lambda package: "1.47.0")
    with pytest.raises(AgentPlatformConfigurationError, match="google-genai>=2.30.1"):
        AgentPlatformConfig.from_env().create_client()


def test_briefing_client_reuses_agent_platform_factory_offline(monkeypatch):
    monkeypatch.setattr(os, "environ", _enterprise_env())
    captured = {}

    def fake_factory(**kwargs):
        captured.update(kwargs)
        return object()

    client = AgentPlatformBriefingLLMClient(AgentPlatformConfig.from_env(), "gemini-3.5-flash-lite", fake_factory)
    client._ensure_client()
    assert client._client is not None
    assert captured["enterprise"] is True


def test_agent_platform_client_preserves_json_and_usage_tracking(monkeypatch):
    monkeypatch.setattr(os, "environ", _enterprise_env())
    import src.signals.llm_briefing as briefing_module
    monkeypatch.setattr(briefing_module, "check_external_llm_allowed", lambda channel: None)

    class FakeModels:
        def generate_content(self, **kwargs):
            assert kwargs["config"].max_output_tokens == 256
            usage = type("Usage", (), {"prompt_token_count": 11, "candidates_token_count": 7, "thinking_token_count": 3})()
            return type("Response", (), {"text": '{"ok": true}', "usage_metadata": usage, "model_version": "fake-agent-model"})()

    class FakeClient:
        models = FakeModels()

    client = AgentPlatformBriefingLLMClient(
        AgentPlatformConfig.from_env(), "gemini-3.5-flash-lite", lambda **kwargs: FakeClient(),
    )
    parsed, metadata = client.generate_json("system", "user", max_output_tokens=256)
    assert parsed == {"ok": True}
    assert metadata["input_tokens"] == 11
    assert metadata["output_tokens"] == 7
    assert metadata["thinking_tokens"] == 3
    assert client.tracker.total_input_tokens == 11


def test_personalization_uses_schema_and_768_output_cap(monkeypatch):
    monkeypatch.setattr(os, "environ", _enterprise_env())
    import src.signals.llm_briefing as briefing_module
    monkeypatch.setattr(briefing_module, "check_external_llm_allowed", lambda channel: None)

    class FakeModels:
        def generate_content(self, **kwargs):
            config = kwargs["config"]
            assert config.max_output_tokens == 768
            assert set(config.response_schema["required"]) >= {
                "source_facts_ko", "user_relevance_ko", "recommendation_reason_ko",
            }
            usage = type("Usage", (), {"prompt_token_count": 12, "candidates_token_count": 20, "thinking_token_count": 0})()
            candidate = type("Candidate", (), {"finish_reason": "STOP"})()
            return type("Response", (), {"text": '{"source_facts_ko":"x"}', "usage_metadata": usage,
                                           "candidates": [candidate], "model_version": "fake-agent-model"})()

    class FakeClient:
        models = FakeModels()

    client = AgentPlatformBriefingLLMClient(
        AgentPlatformConfig.from_env(), "gemini-3.5-flash-lite", lambda **kwargs: FakeClient(),
    )
    parsed, metadata = client.generate_json("system", "user", call_type="personalize", max_output_tokens=768)
    assert parsed == {"source_facts_ko": "x"}
    assert metadata["finish_reason"] == "STOP"
    assert metadata["max_output_tokens"] == 768


def test_content_uses_schema_and_1024_output_cap(monkeypatch):
    monkeypatch.setattr(os, "environ", _enterprise_env())
    import src.signals.llm_briefing as briefing_module
    monkeypatch.setattr(briefing_module, "check_external_llm_allowed", lambda channel: None)

    class FakeModels:
        def generate_content(self, **kwargs):
            config = kwargs["config"]
            assert config.max_output_tokens == 1024
            assert {"display_title_ko", "grounded_facts"} <= set(config.response_schema["required"])
            usage = type("Usage", (), {"prompt_token_count": 12, "candidates_token_count": 20, "thinking_token_count": 0})()
            return type("Response", (), {"text": '{"ok": true}', "usage_metadata": usage, "candidates": []})()

    class FakeClient:
        models = FakeModels()

    client = AgentPlatformBriefingLLMClient(
        AgentPlatformConfig.from_env(), "gemini-3.5-flash-lite", lambda **kwargs: FakeClient(),
    )
    parsed, metadata = client.generate_json("system", "user", call_type="content", max_output_tokens=1024)
    assert parsed == {"ok": True}
    assert metadata["max_output_tokens"] == 1024


def test_truncated_json_is_recorded_and_rejected_without_retry(monkeypatch):
    monkeypatch.setattr(os, "environ", _enterprise_env())
    import src.signals.llm_briefing as briefing_module
    monkeypatch.setattr(briefing_module, "check_external_llm_allowed", lambda channel: None)

    class FakeModels:
        def generate_content(self, **kwargs):
            usage = type("Usage", (), {"prompt_token_count": 12, "candidates_token_count": 768, "thinking_token_count": 0})()
            candidate = type("Candidate", (), {"finish_reason": "MAX_TOKENS"})()
            return type("Response", (), {"text": '{"source_facts_ko":"truncated', "usage_metadata": usage,
                                           "candidates": [candidate]})()

    class FakeClient:
        models = FakeModels()

    client = AgentPlatformBriefingLLMClient(
        AgentPlatformConfig.from_env(), "gemini-3.5-flash-lite", lambda **kwargs: FakeClient(),
    )
    parsed, metadata = client.generate_json("system", "user", call_type="personalize", max_output_tokens=768)
    assert parsed is None
    assert metadata["error_code"] == "json_error"
    assert metadata["json_parse_failure_type"] == "truncated_output"
    assert metadata["finish_reason"] == "MAX_TOKENS"
    assert metadata["retries"] == 0


def test_experiment_uses_one_fake_content_call_without_models_list(monkeypatch):
    """The first live phase is one generation request, never a list preflight."""
    import src.signals.llm_briefing as briefing_module

    source = {"id": "source-1", "title": "Release", "url": "https://example.test/release",
              "published_at": "2026-11-06T00:00:00Z", "summary": "A verified release.",
              "source": "github_release"}
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            calls.append("client")

    def fake_content(item, client):
        calls.append("content")
        return {"status": "success", "content_briefing": {
            "display_title_ko": "릴리스", "display_summary_ko": "검증된 릴리스입니다.",
            "_validation": {"valid": True},
        }, "metadata": {"model": experiment.BASELINE_MODEL, "retries": 0,
                            "input_tokens": 12, "output_tokens": 8, "thinking_tokens": 0}}

    monkeypatch.setattr(briefing_module, "AgentPlatformBriefingLLMClient", FakeClient)
    monkeypatch.setattr(briefing_module, "generate_content_briefing", fake_content)
    monkeypatch.setattr(experiment, "_save_results", lambda result: None)
    result = {"generation_requests": 0, "items": []}
    assert experiment._run_content(result, experiment.BASELINE_MODEL, source, object())
    assert calls == ["client", "content"]
    assert result["generation_requests"] == 1
    assert not hasattr(experiment, "_list_supported_models_once")


def test_experiment_enforces_generation_cap_before_fake_client(monkeypatch):
    source = {"id": "source-1", "title": "Release", "url": "https://example.test/release",
              "published_at": "2026-11-06T00:00:00Z", "summary": "A verified release.",
              "source": "github_release"}
    result = {"generation_requests": experiment.LIMITS["max_requests"], "items": []}
    with pytest.raises(RuntimeError, match="generation request cap"):
        experiment._run_content(result, experiment.BASELINE_MODEL, source, object())

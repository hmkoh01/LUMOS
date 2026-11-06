"""Every real LLM entry point must fail closed in tests and normal app mode."""
import pytest

from src.assistant.llm import GeminiProvider, MockProvider
from src.llm_safety import ExternalLLMCallBlocked
from src.llm_safety import check_external_llm_allowed
from src.signals.llm_briefing import BriefingLLMClient


def test_mock_provider_remains_offline_and_usable():
    answer = MockProvider().generate_answer("q", [], [])
    assert answer


def test_gemini_assistant_is_blocked_before_client_use():
    provider = object.__new__(GeminiProvider)
    with pytest.raises(ExternalLLMCallBlocked):
        provider.generate_answer("q", [], [])


def test_briefing_pilot_is_blocked_before_client_creation():
    with pytest.raises(ExternalLLMCallBlocked):
        BriefingLLMClient(api_key="not-a-real-key").generate_json("system", "user")


def test_dry_run_is_local_and_within_budget():
    from tools.gemini_briefing_experiment import dry_run
    report = dry_run()
    assert report["network_requests"] == 0
    assert report["total_request_cap"] == 24
    assert report["within_krw_3000_budget"] is True


def test_only_approved_experiment_can_pass_global_block(monkeypatch):
    monkeypatch.setenv("LUMOS_BLOCK_EXTERNAL_CALLS", "true")
    monkeypatch.setenv("LUMOS_GEMINI_EXPERIMENT", "approved")
    monkeypatch.setenv("LUMOS_TEST_MODE", "false")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    check_external_llm_allowed("briefing_experiment")
    with pytest.raises(ExternalLLMCallBlocked):
        check_external_llm_allowed("assistant")

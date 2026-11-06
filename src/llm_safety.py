"""Fail-closed guard for every real LLM request.

The Engine v2 safety guard intentionally also requires the Engine feature flag.
That is unsuitable for a one-off experiment, so LLM callers use this narrower
guard instead.  It never enables a normal application path by default.
"""
from __future__ import annotations

import os


class ExternalLLMCallBlocked(RuntimeError):
    """Raised before an LLM client can issue a network request."""


_CHANNEL_ENV = {
    "assistant": "LUMOS_ALLOW_ASSISTANT_LLM",
    "briefing_experiment": "LUMOS_GEMINI_EXPERIMENT",
    "engine_v2": "LUMOS_ENGINE_LLM",
}


def check_external_llm_allowed(channel: str) -> None:
    """Allow only an explicitly approved, non-test LLM channel.

    ``LUMOS_BLOCK_EXTERNAL_CALLS=true`` remains in force for all application
    channels.  The sole exception is the separately approved experiment
    process; it still requires the literal value ``approved`` and cannot
    enable the normal Assistant.
    """
    experiment_approved = (
        channel == "briefing_experiment"
        and os.environ.get("LUMOS_GEMINI_EXPERIMENT", "").strip().lower() == "approved"
    )
    if os.environ.get("LUMOS_BLOCK_EXTERNAL_CALLS", "").lower() == "true" and not experiment_approved:
        raise ExternalLLMCallBlocked("LUMOS_BLOCK_EXTERNAL_CALLS=true")
    if os.environ.get("LUMOS_TEST_MODE", "").lower() == "true" or os.environ.get("PYTEST_CURRENT_TEST"):
        raise ExternalLLMCallBlocked("LLM calls are blocked in tests")

    env_name = _CHANNEL_ENV.get(channel)
    if not env_name:
        raise ExternalLLMCallBlocked(f"unknown LLM channel: {channel}")
    required = "approved" if channel in ("briefing_experiment", "engine_v2") else "true"
    if os.environ.get(env_name, "").strip().lower() != required:
        raise ExternalLLMCallBlocked(f"{env_name} must be {required!r}")

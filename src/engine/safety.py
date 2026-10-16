"""External-call safety guard.

Every code path that would make a real network request MUST call
``check_external_call_allowed()`` before proceeding.  This is the
*second* layer of defence — the first is the config flag
``EngineConfig.external_calls_allowed``.

The guard raises ``ExternalCallBlocked`` unconditionally when the
runtime environment is marked as non-production or when the config
flag is off, even if a real API key happens to be present.
"""

from __future__ import annotations

import os
from typing import Optional

from src.engine.config import EngineConfig


class ExternalCallBlocked(RuntimeError):
    """Raised when an external network call is blocked by the safety guard."""


_FORCE_BLOCK_ENV = "LUMOS_BLOCK_EXTERNAL_CALLS"


def check_external_call_allowed(
    config: EngineConfig,
    *,
    call_description: str = "external API call",
    override_env: Optional[str] = None,
) -> None:
    """Raise ``ExternalCallBlocked`` unless external calls are explicitly allowed.

    Checks (in order):
    1. Environment variable ``LUMOS_BLOCK_EXTERNAL_CALLS=true`` → always blocked.
    2. ``config.external_calls_allowed`` is ``False`` → blocked.
    3. Engine not enabled → blocked.

    This function is intentionally strict: it is easier to relax a guard
    than to add one after an accidental API call.
    """
    env_var = override_env or _FORCE_BLOCK_ENV
    if os.environ.get(env_var, "").lower() == "true":
        raise ExternalCallBlocked(
            f"Blocked {call_description}: {env_var}=true in environment"
        )

    if not config.external_calls_allowed:
        raise ExternalCallBlocked(
            f"Blocked {call_description}: external_calls_allowed is False"
        )

    if not config.enabled:
        raise ExternalCallBlocked(
            f"Blocked {call_description}: engine is not enabled"
        )


def is_test_environment() -> bool:
    """Return True when running inside a test harness."""
    return (
        os.environ.get("LUMOS_TEST_MODE", "").lower() == "true"
        or os.environ.get("PYTEST_CURRENT_TEST") is not None
    )

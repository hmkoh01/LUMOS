"""Pytest-only baseline: never inherit a developer's production auth or LLM mode."""
import os


os.environ["LUMOS_AUTH_MODE"] = "local"
os.environ["LUMOS_ENGINE_V2"] = "false"
os.environ["LUMOS_SCHEDULER_ENABLED"] = "false"
os.environ["LUMOS_EXTERNAL_CALLS"] = "false"
os.environ["LUMOS_BLOCK_EXTERNAL_CALLS"] = "true"
os.environ["LUMOS_TEST_MODE"] = "true"

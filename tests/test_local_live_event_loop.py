"""Regression coverage for Windows local-live startup policy."""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path


def _run_module():
    path = Path(__file__).resolve().parents[1] / "run.py"
    spec = importlib.util.spec_from_file_location("lumos_run_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_local_live_uses_selector_policy_on_windows(monkeypatch):
    module = _run_module()
    installed = []
    sentinel = object()
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.asyncio, "WindowsSelectorEventLoopPolicy", lambda: sentinel)
    monkeypatch.setattr(module.asyncio, "set_event_loop_policy", installed.append)

    assert module._configure_local_live_event_loop() == "selector"
    assert installed == [sentinel]


def test_local_socketpair_and_selector_loop_are_available_offline():
    # This deliberately uses only loopback/socketpair primitives.  It does not
    # contact a provider, start Uvicorn, or touch any LUMOS database.
    import socket

    left, right = socket.socketpair()
    left.close()
    right.close()

    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        previous = asyncio.get_event_loop_policy()
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            loop.close()
        finally:
            asyncio.set_event_loop_policy(previous)

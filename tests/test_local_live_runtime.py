from collections import namedtuple

import run


_Version = namedtuple("Version", "major minor micro")


def test_agent_platform_runtime_accepts_locked_sdk_on_supported_python(monkeypatch):
    monkeypatch.setattr(run.sys, "version_info", _Version(3, 12, 9))
    monkeypatch.setattr(run.sys, "executable", "C:/project/.venv-agent/Scripts/python.exe")
    monkeypatch.setattr(run.importlib.metadata, "version", lambda _: "2.30.1")

    status = run._agent_platform_runtime_status()

    assert status == {
        "python": "3.12.9",
        "executable": "C:/project/.venv-agent/Scripts/python.exe",
        "google_genai": "2.30.1",
        "ready": True,
    }


def test_agent_platform_runtime_rejects_missing_sdk_before_workers_start(monkeypatch):
    monkeypatch.setattr(run.sys, "version_info", _Version(3, 12, 9))
    monkeypatch.setattr(run.importlib.metadata, "version", lambda _: (_ for _ in ()).throw(
        run.importlib.metadata.PackageNotFoundError
    ))

    status = run._agent_platform_runtime_status()

    assert status["google_genai"] == "not-installed"
    assert status["ready"] is False

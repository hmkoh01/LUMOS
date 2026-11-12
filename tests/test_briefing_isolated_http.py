"""Briefing HTTP-to-SQLite checks; this does not stand in for browser E2E."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.engine import router as engine_router
from src.api.signals import router as signals_router
from src.storage.sqlite_store import SQLiteStore


def test_briefing_http_persists_feedback_and_isolates_users(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMOS_ENGINE_V2", "true")
    monkeypatch.setenv("LUMOS_EXTERNAL_CALLS", "false")
    monkeypatch.setenv("LUMOS_BLOCK_EXTERNAL_CALLS", "true")
    monkeypatch.setenv("LUMOS_SCHEDULER_ENABLED", "false")
    store = SQLiteStore(tmp_path / "briefing-test.sqlite")
    user_a = store.get_or_create_user_by_external_id("briefing-test-a")
    user_b = store.get_or_create_user_by_external_id("briefing-test-b")
    selected = {"id": user_a}

    def card(name):
        return {
            "title": name, "summary": "Fixture summary", "why_it_matters": "Fixture",
            "source_name": "Fixture", "source_url": f"https://example.test/{name}",
            "dedupe_key": f"engine-v2:daily:{name}", "rank": 1, "status": "active",
            "source_items_json": [],
            "metadata_json": {"briefing_provider": "engine-v2-structured", "engine_period": "daily"},
        }

    run = store.create_pipeline_run("engine_v2", user_id=user_a)
    signal_a = store.create_signal(card("primary-a"), pipeline_run_id=run, user_id=user_a)
    store.save_signal_reserves(run, [{"_engine_signal": card("reserve-a")}], 1, user_id=user_a)
    run_b = store.create_pipeline_run("engine_v2", user_id=user_b)
    signal_b = store.create_signal(card("primary-b"), pipeline_run_id=run_b, user_id=user_b)
    app = FastAPI()
    app.include_router(signals_router, prefix="/api/v1")
    app.include_router(engine_router, prefix="/api/v1")
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=selected["id"])

    with TestClient(app) as client:
        def feed():
            response = client.get("/api/v1/signals?period=today")
            assert response.status_code == 200
            return response.json()["signals"]

        assert [s["id"] for s in feed()] == [signal_a]
        assert client.put(f"/api/v1/signals/{signal_a}/saved", json={"saved": True}).status_code == 200
        assert feed()[0]["saved"] is True
        response = client.post("/api/v1/engine/briefing/dismiss", json={"signal_id": signal_a, "period": "today"})
        assert response.status_code == 200
        reserve = response.json()["replacement"]
        assert reserve and reserve["title"] == "reserve-a"
        assert [s["id"] for s in feed()] == [reserve["id"]]
        reason = client.put(f"/api/v1/signals/{signal_a}/recommendation-reason", json={"preference": "ignored", "reason_code": "too_technical"})
        assert reason.status_code == 200
        assert store.get_feedback_preference_detail(signal_a, user_id=user_a)["reason_code"] == "too_technical"
        selected["id"] = user_b
        assert [s["id"] for s in feed()] == [signal_b]
        assert client.put(f"/api/v1/signals/{signal_a}/saved", json={"saved": False}).status_code == 400
        selected["id"] = user_a
        assert client.post("/api/v1/engine/briefing/undo-dismiss", json={"signal_id": signal_a}).status_code == 200
        reloaded = feed()
        assert any(s["id"] == signal_a and s["saved"] for s in reloaded)
        assert store.get_signal(signal_b, user_id=user_b)["recommendation_preference"] is None

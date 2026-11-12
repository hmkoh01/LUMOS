"""Stage 4 offline integration: onboarding through feedback-learning controls."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.engine import router as engine_router
from src.api.profile import router as profile_router
from src.api.signals import router as signals_router
from src.context.onboarding import OnboardingService
from src.engine.llm.publisher import publish_engine_cards
from src.engine.models import KoreanBriefing, RawCandidate, ScoredCandidate
from src.sources.router import SourceRouter
from src.storage.sqlite_store import SQLiteStore


def _card(index: int):
    candidate = RawCandidate(
        dedupe_key=f"stage4-{index}", source="fixture", url=f"https://example.test/stage4/{index}",
        title=f"AI 산업 검증 소식 {index}", summary="오프라인 통합 검증용 요약",
        matched_interests=["AI"], metrics={"specificity": "general", "topic_tags": ["AI"]},
    )
    return {
        "candidate": candidate,
        "scored": ScoredCandidate(candidate=candidate, importance_score=1.0 - index * .1, rank=index + 1),
        "rank": index + 1,
        "briefing": KoreanBriefing(
            dedupe_key=candidate.dedupe_key, display_title_ko=candidate.title,
            headline_summary_ko=candidate.summary, key_facts_ko=["검증된 원문 메타데이터"],
        ),
        "recommendation_reason_ko": "AI 산업 뉴스 유형을 선택한 관심사와 직접 연결됩니다.",
        "why_it_matters_ko": "원문에 있는 범위만 표시합니다.",
        "recommended_action_ko": "공식 원문을 확인하세요.",
        "relevance_level": "direct", "relevance_basis": "AI",
    }


def test_stage4_isolated_flow(tmp_path, monkeypatch):
    # Explicitly prevent this integration fixture from starting collection,
    # LLM, translation, or a scheduler.
    monkeypatch.setenv("LUMOS_ENGINE_V2", "true")
    monkeypatch.setenv("LUMOS_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("LUMOS_BLOCK_EXTERNAL_CALLS", "true")
    store = SQLiteStore(tmp_path / "stage4.db")
    saved = OnboardingService(store).save({
        "keywords": ["AI"], "interest_type_preferences": {"AI": ["ai_industry_news"]},
    }, user_id=1)
    assert saved["profile"]["raw_onboarding_json"]["interest_type_preferences"] == {"AI": ["ai_industry_news"]}
    assert set(SourceRouter().classify_interests(store.get_profile(user_id=1), store.get_interests(user_id=1))) == {"AI_TREND"}

    run_id = store.create_pipeline_run("engine_v2", user_id=1)
    published = publish_engine_cards(store, [_card(i) for i in range(4)], user_id=1, period="daily", pipeline_run_id=run_id, display_limit=2)
    assert published["reserve_count"] == 2
    assert len(store.get_engine_signals_for_period("today", limit=5, user_id=1)) == 2

    app = FastAPI()
    app.include_router(engine_router, prefix="/api/v1")
    app.include_router(signals_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/api/v1")
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=1)

    with TestClient(app) as client:
        # Three separate card evaluations produce one conservative preference.
        evaluated = []
        for _ in range(3):
            visible = store.get_engine_signals_for_period("today", limit=5, user_id=1)
            signal_id = visible[0]["id"]
            dismissed = client.post("/api/v1/engine/briefing/dismiss", json={"signal_id": signal_id, "period": "today"})
            assert dismissed.status_code == 200
            assert client.put(
                f"/api/v1/signals/{signal_id}/recommendation-reason",
                json={"preference": "ignored", "reason_code": "too_general"},
            ).status_code == 200
            evaluated.append(signal_id)

        learned = client.get("/api/v1/profile/feedback-learning")
        assert learned.status_code == 200
        assert any(item["label"] == "더 구체적인 정보 선호" for item in learned.json()["preferences"])
        # Reset preserves historical card reactions, but blocks their learning effect.
        assert client.delete("/api/v1/profile/feedback-learning").status_code == 200
        assert client.get("/api/v1/profile/feedback-learning").json()["preferences"] == []
        # Undo remains available through the existing endpoint; it clears the
        # preference without changing explicit onboarding interests.
        assert client.post("/api/v1/engine/briefing/undo-dismiss", json={"signal_id": evaluated[0]}).status_code == 200

    assert store.get_profile(user_id=1)["raw_onboarding_json"]["interest_type_preferences"] == {"AI": ["ai_industry_news"]}
    assert store.get_feedback_preference_details(user_id=2) == []
    assert all(not config["enabled"] for config in store.get_source_configs(user_id=1) if config["source_id"] == "opendart")


def test_learning_schema_is_additive_for_an_existing_fixture_database(tmp_path):
    """Re-opening a pre-learning-shaped DB must not rewrite its profile/feed."""
    path = tmp_path / "existing.db"
    store = SQLiteStore(path)
    OnboardingService(store).save({"keywords": ["AI"]}, user_id=1)
    signal_id = store.create_signal({
        "title": "기존 카드", "summary": "기존 피드", "why_it_matters": "기존 이유",
        "source_name": "검증 출처", "source_url": "https://example.test/existing", "status": "active",
    }, user_id=1)
    profile_before = store.get_profile(user_id=1)
    with store.connect() as conn:
        conn.execute("DROP TABLE feedback_learning_rule_resets")
        conn.execute("DROP TABLE feedback_learning_settings")
        conn.commit()

    upgraded = SQLiteStore(path)
    assert upgraded.get_profile(user_id=1) == profile_before
    assert upgraded.get_signal(signal_id, user_id=1)["title"] == "기존 카드"
    assert upgraded.get_feedback_learning_settings(user_id=1)["enabled"] is True


def test_reason_endpoint_after_engine_dismiss_is_idempotent_and_user_scoped(tmp_path, monkeypatch):
    """The optional reason follows the live dismiss/undo sequence, not a stale card."""
    monkeypatch.setenv("LUMOS_ENGINE_V2", "true")
    store = SQLiteStore(tmp_path / "reason-after-dismiss.db")
    OnboardingService(store).save({"keywords": ["AI"]}, user_id=1)
    run_id = store.create_pipeline_run("engine_v2", user_id=1)
    publish_engine_cards(store, [_card(0)], user_id=1, period="daily", pipeline_run_id=run_id, display_limit=1)
    signal_id = store.get_engine_signals_for_period("today", limit=1, user_id=1)[0]["id"]
    selected = {"id": 1}
    app = FastAPI()
    app.include_router(engine_router, prefix="/api/v1")
    app.include_router(signals_router, prefix="/api/v1")
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=selected["id"])

    with TestClient(app) as client:
        assert client.post("/api/v1/engine/briefing/dismiss", json={"signal_id": signal_id, "period": "today"}).status_code == 200
        initial = client.put(
            f"/api/v1/signals/{signal_id}/recommendation-reason",
            json={"preference": "ignored", "reason_code": "too_general"},
        )
        assert initial.status_code == 200
        changed = client.put(
            f"/api/v1/signals/{signal_id}/recommendation-reason",
            json={"preference": "ignored", "reason_code": "too_technical"},
        )
        assert changed.status_code == 200
        assert changed.json()["data"]["changed"] is True
        duplicate = client.put(
            f"/api/v1/signals/{signal_id}/recommendation-reason",
            json={"preference": "ignored", "reason_code": "too_technical"},
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["data"]["changed"] is False
        assert client.post("/api/v1/engine/briefing/undo-dismiss", json={"signal_id": signal_id}).status_code == 200
        # Undo clears the preference; an old reason click must not be accepted.
        assert client.put(
            f"/api/v1/signals/{signal_id}/recommendation-reason",
            json={"preference": "ignored", "reason_code": "too_technical"},
        ).status_code == 400
        selected["id"] = 2
        assert client.put(
            f"/api/v1/signals/{signal_id}/recommendation-reason",
            json={"preference": "ignored", "reason_code": "too_general"},
        ).status_code == 400

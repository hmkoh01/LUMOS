"""Offline coverage for Stage 3 structured card-feedback reasons."""

import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.signals import router as signals_router
from src.context.onboarding import OnboardingService
from src.signals.feedback import FeedbackService
from src.storage.sqlite_store import SQLiteStore


def _signal(title: str, suffix: str):
    return {
        "title": title,
        "summary": "선호 상세에는 저장하지 않는 오프라인 검증 요약",
        "why_it_matters": "오프라인 검증",
        "source_name": "검증 출처",
        "source_url": f"https://example.test/{suffix}",
        "category": "AI_TREND",
        "status": "active",
        "metadata_json": {
            "matched_keywords": ["AI", "model release"],
            "difficulty": "advanced",
            "data_kind": "official_update",
        },
    }


def test_reason_is_optional_structured_and_does_not_change_explicit_interests():
    directory = tempfile.TemporaryDirectory()
    try:
        store = SQLiteStore(Path(directory.name) / "feedback-reasons.db")
        OnboardingService(store).save({
            "keywords": ["AI"],
            "interest_type_preferences": {"AI": ["ai_industry_news"]},
        }, user_id=1)
        signal_id = store.create_signal(_signal("비공개 검증 제목", "one"), user_id=1)
        before_weight = store.get_interests(user_id=1, limit=None)[0]["weight"]
        service = FeedbackService(store)

        # A preference alone remains valid and has no inferred reason.
        service.set_recommendation_preference(signal_id, "ignored", user_id=1)
        assert store.get_feedback_preference_detail(signal_id, user_id=1) is None
        assert store.get_interests(user_id=1, limit=None)[0]["weight"] == before_weight

        detail = service.set_recommendation_reason(
            signal_id, "ignored", "too_technical", user_id=1
        )["detail"]
        assert detail["preference"] == "ignored"
        assert detail["reason_code"] == "too_technical"
        assert detail["information_type_ids_json"] == ["ai_industry_news"]
        assert detail["topic_tags_json"] == ["AI", "model release"]
        assert "title" not in detail and "summary" not in detail
        assert store.get_interests(user_id=1, limit=None)[0]["weight"] == before_weight

        # Changing the reason updates the one current structured record;
        # clearing/changing the preference removes stale inferred detail.
        service.set_recommendation_reason(signal_id, "ignored", "not_needed_now", user_id=1)
        assert store.get_feedback_preference_detail(signal_id, user_id=1)["reason_code"] == "not_needed_now"
        service.set_recommendation_preference(signal_id, "tracked", user_id=1)
        assert store.get_feedback_preference_detail(signal_id, user_id=1) is None
        service.set_recommendation_preference(signal_id, None, user_id=1)
        assert store.get_feedback_preference_detail(signal_id, user_id=1) is None
    finally:
        directory.cleanup()


def test_reason_api_is_user_scoped_and_requires_matching_current_preference():
    directory = tempfile.TemporaryDirectory()
    try:
        store = SQLiteStore(Path(directory.name) / "feedback-reasons-api.db")
        with store.connect() as conn:
            conn.execute("INSERT INTO users (external_id) VALUES ('reason-a')")
            conn.execute("INSERT INTO users (external_id) VALUES ('reason-b')")
            user_a = conn.execute("SELECT id FROM users WHERE external_id = 'reason-a'").fetchone()[0]
            user_b = conn.execute("SELECT id FROM users WHERE external_id = 'reason-b'").fetchone()[0]
        signal_id = store.create_signal(_signal("사용자 A 검증 제목", "a"), user_id=user_a)
        service = FeedbackService(store)
        service.set_recommendation_preference(signal_id, "tracked", user_id=user_a)
        selected = {"id": user_a}
        app = FastAPI()
        app.include_router(signals_router, prefix="/api/v1")
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=selected["id"])
        with TestClient(app) as client:
            saved = client.put(
                f"/api/v1/signals/{signal_id}/recommendation-reason",
                json={"preference": "tracked", "reason_code": "practical_useful"},
            )
            assert saved.status_code == 200
            duplicate = client.put(
                f"/api/v1/signals/{signal_id}/recommendation-reason",
                json={"preference": "tracked", "reason_code": "practical_useful"},
            )
            assert duplicate.status_code == 200
            assert duplicate.json()["data"]["changed"] is False
            mismatch = client.put(
                f"/api/v1/signals/{signal_id}/recommendation-reason",
                json={"preference": "ignored", "reason_code": "too_general"},
            )
            assert mismatch.status_code == 400
            selected["id"] = user_b
            other_user = client.put(
                f"/api/v1/signals/{signal_id}/recommendation-reason",
                json={"preference": "tracked", "reason_code": "timely"},
            )
            assert other_user.status_code == 400
    finally:
        directory.cleanup()


def test_summary_requires_repeated_consistent_feedback_before_future_use():
    directory = tempfile.TemporaryDirectory()
    try:
        store = SQLiteStore(Path(directory.name) / "feedback-summary.db")
        service = FeedbackService(store)
        for index in range(3):
            signal_id = store.create_signal(_signal(f"검증 제목 {index}", str(index)), user_id=1)
            service.set_recommendation_preference(signal_id, "ignored", user_id=1)
            service.set_recommendation_reason(signal_id, "ignored", "too_general", user_id=1)
        summary = store.get_inferred_preference_summary(user_id=1)
        assert len(summary) == 1
        assert summary[0]["event_count"] == 3
        assert summary[0]["eligible_for_future_ranking"] is True
        # Aggregation stays diagnostic-only: it has no ranker or interest write.
        assert store.get_interests(user_id=1, limit=None) == []
    finally:
        directory.cleanup()

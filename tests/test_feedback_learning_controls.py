"""Offline controls for Stage 3 learning; production ranking stays disabled."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.profile import router as profile_router
from src.context.onboarding import OnboardingService
from src.engine.models import RawCandidate, ScoredCandidate
from src.engine.personalization.feedback_experiment import (
    compare_feedback_rankings, derive_feedback_rules, feedback_experiment_opt_in_allowed,
)
from src.signals.feedback import FeedbackService
from src.storage.sqlite_store import SQLiteStore


def _signal(index, category="AI_TREND", *, run_id=None, topic="topic-a", difficulty="unknown"):
    return {
        "pipeline_run_id": run_id, "title": f"검증용 소식 {index}", "summary": "오프라인 검증용 요약",
        "why_it_matters": "오프라인 검증", "source_name": "검증 출처", "source_url": f"https://example.test/{index}",
        "category": category, "status": "active",
        "metadata_json": {"matched_keywords": [topic], "difficulty": difficulty, "data_kind": "fixture"},
    }


def _rate(store, index, preference, reason, **kwargs):
    signal_id = store.create_signal(_signal(index, **kwargs), pipeline_run_id=kwargs.get("run_id"), user_id=1)
    service = FeedbackService(store)
    service.set_recommendation_preference(signal_id, preference, user_id=1)
    service.set_recommendation_reason(signal_id, preference, reason, user_id=1)
    return signal_id


def _candidate(key, score, *, topic="topic-a", category="AI_TREND", specificity="unknown"):
    return ScoredCandidate(RawCandidate(
        dedupe_key=key, source="fixture", title=f"{category} {key}", summary="fixture",
        matched_interests=["AI"],
        metrics={"topic_tags": [topic], "specificity": specificity, "data_kind": category},
    ), score)


def _store():
    directory = tempfile.TemporaryDirectory()
    store = SQLiteStore(Path(directory.name) / "feedback-controls.db")
    OnboardingService(store).save({
        "keywords": ["AI", "마케팅", "데이터", "인턴"],
        "interest_type_preferences": {"AI": ["ai_industry_news"], "마케팅": ["marketing_technology"],
                                      "데이터": ["data_analysis"], "인턴": ["intern_jobs"]},
    }, user_id=1)
    return directory, store


def test_controls_are_user_scoped_and_reset_keeps_history_but_blocks_old_rules():
    directory, store = _store()
    try:
        for index in range(3):
            _rate(store, index, "ignored", "too_general")
        assert derive_feedback_rules(store.get_feedback_preference_details(user_id=1))
        before = store.get_interests(user_id=1, limit=None)
        feedback_count = len(store.get_feedback_preference_details(user_id=1))
        store.reset_feedback_learning(user_id=1)
        settings = store.get_feedback_learning_settings(user_id=1)
        assert settings["reset_at"]
        assert derive_feedback_rules(store.get_feedback_preference_details(user_id=1), reset_at=settings["reset_at"]) == []
        assert len(store.get_feedback_preference_details(user_id=1)) == feedback_count
        assert store.get_interests(user_id=1, limit=None) == before
        store.set_feedback_learning_enabled(False, user_id=1)
        result = compare_feedback_rankings(store, 1, [_candidate("specific", .7, specificity="specific")], ["AI"])
        assert result["user_learning_enabled"] is False
        assert result["rules"] == []
        assert store.get_feedback_learning_settings(user_id=2)["enabled"] is True
    finally:
        directory.cleanup()


def test_individual_reset_does_not_rebuild_from_pre_reset_evidence():
    directory, store = _store()
    try:
        ids = [_rate(store, index, "ignored", "too_technical", difficulty="advanced") for index in range(3)]
        assert any(rule.feature == "difficulty" for rule in derive_feedback_rules(store.get_feedback_preference_details(user_id=1)))
        store.reset_feedback_learning(user_id=1, feature="difficulty", value="advanced")
        rules = derive_feedback_rules(
            store.get_feedback_preference_details(user_id=1),
            rule_resets=store.get_feedback_learning_rule_resets(user_id=1),
        )
        assert not any(rule.feature == "difficulty" and rule.value == "advanced" for rule in rules)
        # No preference is inferred from three cards in one run at max strength.
        with store.connect() as conn:
            conn.executemany("UPDATE signals SET pipeline_run_id = 77 WHERE id = ?", [(item,) for item in ids])
            conn.commit()
        future = (datetime.now(timezone.utc) + timedelta(seconds=2)).replace(tzinfo=None).isoformat(sep=" ")
        with store.connect() as conn:
            conn.executemany("UPDATE feedback_preference_details SET updated_at = ? WHERE signal_id = ?", [(future, item) for item in ids])
            conn.commit()
        rules = derive_feedback_rules(store.get_feedback_preference_details(user_id=1), rule_resets=store.get_feedback_learning_rule_resets(user_id=1))
        rule = next(rule for rule in rules if rule.feature == "difficulty")
        assert -0.05 < rule.adjustment < 0  # one briefing run is capped to one vote
    finally:
        directory.cleanup()


def test_diverse_offline_comparison_never_adds_candidates_or_changes_explicit_constraints():
    directory, store = _store()
    try:
        # Three separate marketing cards provide evidence for a specific item,
        # but cannot activate a source or add a different-type candidate.
        for index in range(3):
            _rate(store, index, "ignored", "too_general", category="MARKETING_TECH", topic="marketing", run_id=100 + index)
        candidates = [
            _candidate("marketing-general", .80, topic="marketing", category="MARKETING_TECH", specificity="general"),
            _candidate("marketing-specific", .75, topic="marketing", category="MARKETING_TECH", specificity="specific"),
            _candidate("unrelated-job", .99, topic="intern", category="CAREER", specificity="specific"),
        ]
        before_interests = store.get_interests(user_id=1, limit=None)
        result = compare_feedback_rankings(store, 1, candidates, ["마케팅"], display_limit=3)
        assert {card["dedupe_key"] for card in result["feedback_ranked"]} <= {"marketing-general", "marketing-specific", "unrelated-job"}
        assert store.get_interests(user_id=1, limit=None) == before_interests
        assert result["production_enabled"] is False
        assert all(not source["enabled"] for source in store.get_source_configs(user_id=1) if source["source_id"] == "opendart")
    finally:
        directory.cleanup()


def test_ai_data_and_job_fixtures_keep_candidate_pool_and_source_constraints():
    directory, store = _store()
    try:
        for topic, category in (("AI", "AI_TREND"), ("data", "DATA_INDUSTRY"), ("intern", "CAREER")):
            for index in range(3):
                _rate(store, f"{topic}-{index}", "ignored", "too_general", topic=topic, category=category, run_id=200 + index)
            candidates = [
                _candidate(f"{topic}-general", .8, topic=topic, category=category, specificity="general"),
                _candidate(f"{topic}-specific", .75, topic=topic, category=category, specificity="specific"),
            ]
            result = compare_feedback_rankings(store, 1, candidates, [topic], display_limit=2)
            assert {card["dedupe_key"] for card in result["feedback_ranked"]} == {item.candidate.dedupe_key for item in candidates}
            assert result["production_enabled"] is False
        assert not feedback_experiment_opt_in_allowed(1, {})
        assert not feedback_experiment_opt_in_allowed(1, {"LUMOS_FEEDBACK_RANKING_EXPERIMENT_ENABLED": "true"})
        assert feedback_experiment_opt_in_allowed(1, {
            "LUMOS_FEEDBACK_RANKING_EXPERIMENT_ENABLED": "true",
            "LUMOS_FEEDBACK_RANKING_EXPERIMENT_USER_IDS": "1",
        })
    finally:
        directory.cleanup()


def test_learning_api_exposes_simple_labels_and_reset_without_card_text():
    directory, store = _store()
    try:
        for index in range(3):
            _rate(store, index, "ignored", "too_general")
        app = FastAPI()
        app.include_router(profile_router, prefix="/api/v1")
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=1)
        with TestClient(app) as client:
            response = client.get("/api/v1/profile/feedback-learning")
            assert response.status_code == 200
            body = response.json()
            assert body["production_enabled"] is False
            assert body["preferences"][0]["label"] == "더 구체적인 정보 선호"
            assert "adjustment" not in body["preferences"][0]
            assert client.put("/api/v1/profile/feedback-learning", json={"enabled": False}).status_code == 200
            assert client.delete("/api/v1/profile/feedback-learning").status_code == 200
            assert client.get("/api/v1/profile/feedback-learning").json()["enabled"] is False
    finally:
        directory.cleanup()


def test_feedback_management_keeps_the_structured_reason_with_the_user_feedback_list():
    directory, store = _store()
    try:
        _rate(store, "reason-visible", "ignored", "too_general")
        feedback = store.get_feedback_signals("ignored", user_id=1)
        assert len(feedback) == 1
        assert feedback[0]["feedback_reason_code"] == "too_general"
        # A new user's default remains automatic; no UI opt-in is required.
        assert store.get_feedback_learning_settings(user_id=2)["enabled"] is True
    finally:
        directory.cleanup()

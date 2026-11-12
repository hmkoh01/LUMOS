"""Fixture-only A/B checks for the disabled accumulated-feedback ranker."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.context.onboarding import OnboardingService
from src.engine.models import RawCandidate, ScoredCandidate
from src.engine.personalization.feedback_experiment import (
    MAX_SCORE_ADJUSTMENT,
    apply_feedback_experiment,
    compare_feedback_rankings,
    derive_feedback_rules,
)
from src.signals.feedback import FeedbackService
from src.storage.sqlite_store import SQLiteStore


def _candidate(key: str, score: float, *, specificity="unknown", difficulty="unknown", topic="topic-a"):
    return ScoredCandidate(
        candidate=RawCandidate(
            dedupe_key=key,
            source="fixture",
            title=f"AI {key}",
            summary="fixture only",
            matched_interests=["AI"],
            metrics={"topic_tags": [topic], "specificity": specificity, "difficulty": difficulty},
        ),
        importance_score=score,
    )


def _signal(index: int, *, topic="topic-a", difficulty="unknown"):
    return {
        "title": f"fixture {index}", "summary": "fixture", "why_it_matters": "fixture",
        "source_name": "fixture", "source_url": f"https://example.test/{index}",
        "category": "AI_TREND", "status": "active",
        "metadata_json": {"matched_keywords": [topic], "difficulty": difficulty, "data_kind": "official_update"},
    }


def _store():
    directory = tempfile.TemporaryDirectory()
    store = SQLiteStore(Path(directory.name) / "ranking-experiment.db")
    OnboardingService(store).save({
        "keywords": ["AI"], "interest_type_preferences": {"AI": ["ai_industry_news"]},
    }, user_id=1)
    return directory, store


def _rate(store, index: int, preference: str, reason: str, **kwargs):
    service = FeedbackService(store)
    signal_id = store.create_signal(_signal(index, **kwargs), user_id=1)
    service.set_recommendation_preference(signal_id, preference, user_id=1)
    service.set_recommendation_reason(signal_id, preference, reason, user_id=1)
    return signal_id


def test_one_feedback_event_keeps_fixture_ranking_unchanged():
    directory, store = _store()
    try:
        _rate(store, 1, "ignored", "too_general")
        candidates = [_candidate("general", .80, specificity="general"), _candidate("specific", .75, specificity="specific")]
        result = compare_feedback_rankings(store, 1, candidates, ["AI"], display_limit=2)
        assert result["enabled"] is False
        assert result["rules"] == []
        assert result["rank_changes"] == []
    finally:
        directory.cleanup()


def test_three_distinct_consistent_reasons_change_only_matching_candidate_score():
    directory, store = _store()
    try:
        for index in range(3):
            _rate(store, index, "ignored", "too_general")
        candidates = [_candidate("general", .80, specificity="general"), _candidate("specific", .75, specificity="specific")]
        result = compare_feedback_rankings(store, 1, candidates, ["AI"], display_limit=2)
        assert result["baseline"][0]["dedupe_key"] == "general"
        assert result["feedback_ranked"][0]["dedupe_key"] == "specific"
        assert result["rank_changes"]
        assert result["diagnostics"]
        assert all(abs(item["score_delta"]) <= MAX_SCORE_ADJUSTMENT for item in result["diagnostics"])
        # The actual candidate pool remains exactly the supplied pool.
        assert {item["dedupe_key"] for item in result["feedback_ranked"]} == {"general", "specific"}
    finally:
        directory.cleanup()


def test_conflicting_feedback_is_inconclusive_and_does_not_create_rule():
    directory, store = _store()
    try:
        for index in range(3):
            _rate(store, index, "ignored", "unrelated_subtopic", topic="topic-a")
        for index in range(3, 6):
            _rate(store, index, "tracked", "practical_useful", topic="topic-a")
        rules = derive_feedback_rules(store.get_feedback_preference_details(user_id=1))
        assert not [rule for rule in rules if rule.feature == "topic" and rule.value == "topic-a"]
    finally:
        directory.cleanup()


def test_old_feedback_is_discounted_and_difficulty_feedback_never_changes_interest():
    directory, store = _store()
    try:
        signal_ids = [_rate(store, index, "ignored", "too_technical", difficulty="advanced") for index in range(3)]
        old_time = (datetime.now(timezone.utc) - timedelta(days=180)).replace(tzinfo=None).isoformat(sep=" ")
        with store.connect() as conn:
            conn.executemany(
                "UPDATE feedback_preference_details SET updated_at = ? WHERE signal_id = ? AND user_id = 1",
                [(old_time, signal_id) for signal_id in signal_ids],
            )
            conn.commit()
        before = store.get_interests(user_id=1, limit=None)[0]
        rules = derive_feedback_rules(store.get_feedback_preference_details(user_id=1))
        rule = next(rule for rule in rules if rule.feature == "difficulty")
        assert 0 > rule.adjustment > -MAX_SCORE_ADJUSTMENT
        _, diagnostics = apply_feedback_experiment([_candidate("advanced", .8, difficulty="advanced")], rules, enabled=True)
        assert diagnostics[0]["score_delta"] < 0
        after = store.get_interests(user_id=1, limit=None)[0]
        assert after["keyword"] == before["keyword"]
        assert after["weight"] == before["weight"]
    finally:
        directory.cleanup()


def test_experiment_is_user_scoped_and_never_activates_sources_or_applies_when_disabled():
    directory, store = _store()
    try:
        for index in range(3):
            _rate(store, index, "ignored", "too_general")
        candidates = [_candidate("specific", .7, specificity="specific")]
        rules = derive_feedback_rules(store.get_feedback_preference_details(user_id=1))
        untouched, diagnostics = apply_feedback_experiment(candidates, rules, enabled=False)
        assert diagnostics == []
        assert untouched[0].importance_score == candidates[0].importance_score
        assert store.get_feedback_preference_details(user_id=999) == []
        # No source config write or permission change is part of the experiment.
        assert all(not config["enabled"] for config in store.get_source_configs(user_id=1) if config["source_id"] == "opendart")
    finally:
        directory.cleanup()

from src.engine.llm.publisher import publish_engine_cards
from src.engine.llm.service import card_policy_versions
from src.engine.models import RawCandidate, ScoredCandidate
from src.storage.sqlite_store import SQLiteStore
from datetime import date


def _card(key: str, rank: int):
    candidate = RawCandidate(
        dedupe_key=key, source="github", url=f"https://example.test/{key}",
        title=key, summary="AI agent update", published_at=date.today().isoformat(),
    )
    return {
        "candidate": candidate, "scored": ScoredCandidate(candidate=candidate, importance_score=.8, rank=rank),
        "rank": rank,
        "briefing": type("Briefing", (), {"display_title_ko": key, "headline_summary_ko": "summary", "key_facts_ko": ["fact"]})(),
        "recommendation_reason_ko": "source fact", "why_it_matters_ko": "why", "recommended_action_ko": "read",
        "relevance_level": "direct", "relevance_basis": "AI agent",
    }


def test_new_period_snapshot_replaces_feed_but_keeps_saved_history(tmp_path):
    store = SQLiteStore(tmp_path / "app.sqlite")
    first_run = store.create_pipeline_run("engine_v2", user_id=1)
    publish_engine_cards(store, [_card("old", 1), _card("keep", 2)], user_id=1, period="daily", pipeline_run_id=first_run, display_limit=2)
    old = next(row for row in store.get_engine_signals_for_period("today", limit=2, user_id=1) if row["title"] == "old")
    store.set_saved_signal(old["id"], True, user_id=1)

    second_run = store.create_pipeline_run("engine_v2", user_id=1)
    result = publish_engine_cards(store, [_card("keep", 1), _card("new", 2)], user_id=1, period="daily", pipeline_run_id=second_run, display_limit=2)

    assert result["created"] == 1
    assert result["retained"] == 1
    assert [row["title"] for row in store.get_engine_signals_for_period("today", limit=2, user_id=1)] == ["keep", "new"]
    assert [row["title"] for row in store.get_saved_signals(user_id=1)] == ["old"]


def test_publisher_keeps_card_policy_versions_for_future_web_card_traceability(tmp_path):
    store = SQLiteStore(tmp_path / "app.sqlite")
    run_id = store.create_pipeline_run("engine_v2", user_id=1)
    card = _card("policy", 1)
    card["card_policy_versions"] = {
        "content_prompt": "v7", "personalization_prompt": "v8", "validator": "v8",
    }
    publish_engine_cards(store, [card], user_id=1, period="daily", pipeline_run_id=run_id, display_limit=1)
    signal = store.get_engine_signals_for_period("today", limit=1, user_id=1)[0]
    assert signal["metadata_json"]["card_policy_versions"] == card["card_policy_versions"]


def test_ignored_article_key_is_available_to_all_engine_periods_but_remains_user_scoped(tmp_path):
    store = SQLiteStore(tmp_path / "app.sqlite")
    daily_run = store.create_pipeline_run("engine_v2", user_id=1)
    publish_engine_cards(store, [_card("shared-article", 1)], user_id=1, period="daily", pipeline_run_id=daily_run, display_limit=1)
    dismissed = store.get_engine_signals_for_period("today", limit=1, user_id=1)[0]
    store.set_recommendation_preference(dismissed["id"], "ignored", user_id=1)

    assert store.get_engine_preference_keys("daily", "ignored", user_id=1) == ["shared-article"]
    assert store.get_engine_preference_keys("weekly", "ignored", user_id=1, across_periods=True) == ["shared-article"]
    assert store.get_engine_preference_keys("weekly", "ignored", user_id=2, across_periods=True) == []


def test_incomplete_generation_preserves_only_current_policy_current_period_cards(tmp_path):
    store = SQLiteStore(tmp_path / "app.sqlite")
    first_run = store.create_pipeline_run("engine_v2", user_id=1)
    current = _card("current", 1)
    current["card_policy_versions"] = card_policy_versions()
    legacy = _card("legacy", 2)  # no policy evidence: must not survive a failed run
    publish_engine_cards(store, [current, legacy], user_id=1, period="daily", pipeline_run_id=first_run, display_limit=2)

    second_run = store.create_pipeline_run("engine_v2", user_id=1)
    result = publish_engine_cards(
        store, [], user_id=1, period="daily", pipeline_run_id=second_run, display_limit=2,
        preserve_existing_on_incomplete=True, expected_card_policy_versions=card_policy_versions(),
    )

    assert result["preserved"] == 1
    assert result["archived"] == 1
    active = store.get_engine_signals_for_period("today", limit=5, user_id=1)
    assert [row["title"] for row in active] == ["current"]


def test_normal_empty_result_still_reconciles_to_an_empty_period(tmp_path):
    store = SQLiteStore(tmp_path / "app.sqlite")
    first_run = store.create_pipeline_run("engine_v2", user_id=1)
    card = _card("current", 1)
    card["card_policy_versions"] = card_policy_versions()
    publish_engine_cards(store, [card], user_id=1, period="daily", pipeline_run_id=first_run, display_limit=1)

    second_run = store.create_pipeline_run("engine_v2", user_id=1)
    result = publish_engine_cards(store, [], user_id=1, period="daily", pipeline_run_id=second_run, display_limit=1)

    assert result["preserved"] == 0
    assert result["archived"] == 1
    assert store.get_engine_signals_for_period("today", limit=5, user_id=1) == []


def test_incomplete_generation_never_restores_an_ignored_card(tmp_path):
    store = SQLiteStore(tmp_path / "app.sqlite")
    first_run = store.create_pipeline_run("engine_v2", user_id=1)
    card = _card("ignored", 1)
    card["card_policy_versions"] = card_policy_versions()
    publish_engine_cards(store, [card], user_id=1, period="daily", pipeline_run_id=first_run, display_limit=1)
    signal = store.get_engine_signals_for_period("today", limit=1, user_id=1)[0]
    store.set_recommendation_preference(signal["id"], "ignored", user_id=1)

    second_run = store.create_pipeline_run("engine_v2", user_id=1)
    result = publish_engine_cards(
        store, [], user_id=1, period="daily", pipeline_run_id=second_run, display_limit=1,
        preserve_existing_on_incomplete=True, expected_card_policy_versions=card_policy_versions(),
    )

    assert result["preserved"] == 0
    assert result["archived"] == 1
    assert store.get_engine_preference_keys("daily", "ignored", user_id=1) == ["ignored"]

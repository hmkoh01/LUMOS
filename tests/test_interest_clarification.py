"""Offline coverage for the optional broad-interest onboarding step."""

import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.context import router as context_router
from src.api.profile import router as profile_router
from src.context.onboarding import OnboardingService
from src.engine.collection.source_support import collection_support
from src.sources.interest_clarification import clarification_for_interest
from src.sources.router import SourceRouter
from src.storage.sqlite_store import SQLiteStore


def _store():
    directory = tempfile.TemporaryDirectory()
    return directory, SQLiteStore(Path(directory.name) / "clarification.db")


def test_broad_profiles_use_stable_information_types_and_specific_terms_skip():
    ai = clarification_for_interest("  AI  ")
    marketing = clarification_for_interest("\ub9c8\ucf00\ud305")
    data = clarification_for_interest("DATA")

    assert ai["id"] == "ai"
    assert {choice["id"] for choice in ai["options"]} == {
        "ai_industry_news", "ai_product_updates", "research_papers", "ai_career_education",
    }
    assert {choice["id"] for choice in marketing["options"]} == {
        "marketing_campaign_cases", "marketing_technology", "market_consumer_trends", "career_preparation",
    }
    assert {choice["id"] for choice in data["options"]} == {
        "data_analysis", "data_engineering", "data_industry_news", "career_preparation",
    }
    assert clarification_for_interest("AI \uc624\ud508\uc18c\uc2a4") is None
    assert clarification_for_interest("\ub370\uc774\ud130 \uc5d4\uc9c0\ub2c8\uc5b4\ub9c1") is None
    assert clarification_for_interest("AI \uc0b0\uc5c5 \ub274\uc2a4") is None


def test_selected_clarification_constrains_router_without_inventing_a_fallback():
    router = SourceRouter()
    profile = {"raw_onboarding_json": {"interest_type_preferences": {
        "AI": ["ai_industry_news"],
        "\ub9c8\ucf00\ud305": ["marketing_technology"],
        "\ub370\uc774\ud130": ["data_industry_news"],
    }}}

    assert set(router.classify_interests(profile, [{"keyword": "AI", "status": "active"}])) == {"AI_TREND"}
    assert set(router.classify_interests(profile, [{"keyword": "\ub9c8\ucf00\ud305", "status": "active"}])) == {"MARKETING_TECH"}
    assert set(router.classify_interests(profile, [{"keyword": "\ub370\uc774\ud130", "status": "active"}])) == {"DATA_INDUSTRY"}


def test_preview_is_read_only_and_only_marks_broad_terms_for_clarification():
    directory, store = _store()
    try:
        app = FastAPI()
        app.include_router(profile_router, prefix="/api/v1")
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=1)
        before = store.get_profile(user_id=1)
        with TestClient(app) as client:
            response = client.post("/api/v1/onboarding/preview", json={
                "keywords": ["AI", "\ub9c8\ucf00\ud305", "\ub370\uc774\ud130", "AI \uc624\ud508\uc18c\uc2a4"],
                "interest_type_preferences": {"AI": ["ai_industry_news"]},
            })
        assert response.status_code == 200
        items = {item["keyword"]: item for item in response.json()["interests"]}
        assert items["AI"]["clarification"]["needed"] is True
        assert items["\ub9c8\ucf00\ud305"]["clarification"]["needed"] is True
        assert items["\ub370\uc774\ud130"]["clarification"]["needed"] is True
        assert items["AI \uc624\ud508\uc18c\uc2a4"]["clarification"]["needed"] is False
        assert items["AI"]["availability"]["can_generate_initial_briefing"] is False
        assert store.get_profile(user_id=1) == before
    finally:
        directory.cleanup()


def test_save_preserves_original_interest_and_optional_selection_can_be_skipped():
    directory, store = _store()
    try:
        result = OnboardingService(store).save({
            "keywords": ["AI", "\ub9c8\ucf00\ud305"],
            "interest_type_preferences": {"AI": ["ai_product_updates"]},
        })
        assert [interest["keyword"] for interest in result["interest_graph"]] == ["AI", "\ub9c8\ucf00\ud305"]
        assert result["profile"]["raw_onboarding_json"]["interest_type_preferences"] == {
            "AI": ["ai_product_updates"],
        }
    finally:
        directory.cleanup()


def test_existing_user_can_replace_or_clear_choices_without_changing_interests():
    directory, store = _store()
    try:
        OnboardingService(store).save({
            "keywords": [" AI ", "\ub9c8\ucf00\ud305", "\ub370\uc774\ud130 \uc5d4\uc9c0\ub2c8\uc5b4\ub9c1"],
            "goals": ["keep"],
            "interest_type_preferences": {"AI": ["ai_open_source"]},
        }, user_id=7)
        app = FastAPI()
        app.include_router(profile_router, prefix="/api/v1")
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=7)
        with TestClient(app) as client:
            response = client.put("/api/v1/profile/information-type-preferences", json={
                "interest_type_preferences": {
                    " ai ": ["ai_industry_news"],
                    "\ub9c8\ucf00\ud305": ["marketing_technology"],
                    "other user interest": ["research_papers"],
                }
            })
            assert response.status_code == 200
            profile = response.json()["profile"]
            assert profile["raw_onboarding_json"]["interest_type_preferences"] == {
                "AI": ["ai_industry_news"],
                "\ub9c8\ucf00\ud305": ["marketing_technology"],
            }
            assert profile["raw_onboarding_json"]["information_type_preferences_configured"] is True
            assert profile["goals_json"] == ["keep"]
            assert [item["keyword"] for item in store.get_interests(user_id=7, limit=None)] == [
                "AI", "\ub9c8\ucf00\ud305", "\ub370\uc774\ud130 \uc5d4\uc9c0\ub2c8\uc5b4\ub9c1",
            ]
            cleared = client.put("/api/v1/profile/information-type-preferences", json={
                "interest_type_preferences": {}
            })
            assert cleared.status_code == 200
            assert cleared.json()["profile"]["raw_onboarding_json"]["interest_type_preferences"] == {}
    finally:
        directory.cleanup()


def test_interest_view_metadata_uses_existing_type_labels_without_claiming_source_support():
    directory, store = _store()
    try:
        OnboardingService(store).save({
            "keywords": ["AI", "인턴"],
            "interest_type_preferences": {"AI": ["ai_industry_news", "ai_product_updates"], "인턴": ["internships"]},
        }, user_id=7)
        app = FastAPI()
        app.include_router(context_router, prefix="/api/v1")
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=7)
        with TestClient(app) as client:
            response = client.get("/api/v1/interests", params={"include_muted": "true"})
        assert response.status_code == 200
        interests = {item["keyword"]: item for item in response.json()["interests"]}
        assert interests["AI"]["information_type_labels"] == ["AI 산업 뉴스", "제품·모델 발표"]
        assert {item["id"] for item in interests["AI"]["information_type_options"]} >= {
            "ai_industry_news", "ai_product_updates",
        }
        # A reader-facing label is separate from the operational-source gate.
        assert interests["인턴"]["collection_support"]["status"] != "supported"
        assert interests["인턴"]["information_type_labels"] == ["인턴"]
    finally:
        directory.cleanup()


def test_specific_interest_keeps_router_defined_type_options_without_live_source_claim():
    directory, store = _store()
    try:
        OnboardingService(store).save({
            "keywords": ["AI 에이전트"],
            "interest_type_preferences": {"AI 에이전트": ["ai_product_updates"]},
        }, user_id=7)
        app = FastAPI()
        app.include_router(context_router, prefix="/api/v1")
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=7)
        with TestClient(app) as client:
            response = client.get("/api/v1/interests")
        assert response.status_code == 200
        interest = response.json()["interests"][0]
        assert interest["information_type_labels"] == ["제품·모델 발표"]
        assert {item["id"] for item in interest["information_type_options"]} >= {
            "ai_industry_news", "ai_product_updates",
        }
        assert interest["collection_support"]["status"] != "supported"
    finally:
        directory.cleanup()


def test_specific_interest_never_replaces_a_precise_saved_type_with_unrelated_bucket_options():
    directory, store = _store()
    try:
        OnboardingService(store).save({
            "keywords": ["개발자 도구"],
            "interest_type_preferences": {"개발자 도구": ["developer_tools"]},
        }, user_id=7)
        app = FastAPI()
        app.include_router(context_router, prefix="/api/v1")
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=7)
        with TestClient(app) as client:
            response = client.get("/api/v1/interests")
        assert response.status_code == 200
        interest = response.json()["interests"][0]
        assert [item["id"] for item in interest["information_type_options"]] == ["developer_tools"]
        assert interest["information_type_labels"] == ["개발 도구"]
    finally:
        directory.cleanup()


def test_structured_empty_choice_does_not_restore_legacy_labels_to_other_routes():
    router = SourceRouter()
    profile = {
        "interest_types_json": ["\uc624\ud508\uc18c\uc2a4"],
        "raw_onboarding_json": {
            "interest_type_preferences": {},
            "information_type_preferences_configured": True,
        },
    }
    categories = router.classify_interests(profile, [{"keyword": "AI", "status": "active"}])
    assert "AI_OPEN_SOURCE" not in categories
    assert "AI_TREND" in categories


def test_precise_types_do_not_claim_unrelated_live_sources():
    # A generic community/developer pilot cannot become a marketing or data
    # industry feed merely because the reader chose a similarly broad term.
    profile = {"raw_onboarding_json": {"interest_type_preferences": {
        "\ub9c8\ucf00\ud305": ["marketing_technology"],
        "\ub370\uc774\ud130": ["data_industry_news"],
        "\uc778\ud134": ["internships"],
    }}}
    assert collection_support("\ub9c8\ucf00\ud305", ("github", "hackernews"), profile=profile)["sources"] == []
    assert collection_support("\ub370\uc774\ud130", ("github", "hackernews"), profile=profile)["sources"] == []
    assert collection_support("\uc778\ud134", ("github", "hackernews"), profile=profile)["sources"] == []

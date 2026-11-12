import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.profile import router as profile_router
from src.context.onboarding import OnboardingService
from src.engine.collection.source_support import collection_support
from src.sources.router import SourceRouter
from src.storage.sqlite_store import SQLiteStore


def _store():
    directory = tempfile.TemporaryDirectory()
    return directory, SQLiteStore(Path(directory.name) / "onboarding-types.db")


def test_structured_type_preferences_are_saved_without_creating_fake_interests():
    directory, store = _store()
    try:
        result = OnboardingService(store).save({
            "keywords": ["AI", "신입 개발자 취업"],
            "interest_type_preferences": {
                "AI": ["ai_open_source", "research_papers", "unknown"],
                "신입 개발자 취업": ["junior_jobs", "internships"],
                "not a keyword": ["economic_news"],
            },
            "source_hints": ["https://newsletter.example", "@official"],
        })
        profile = result["profile"]
        assert profile["raw_onboarding_json"]["interest_type_preferences"] == {
            "AI": ["ai_open_source", "research_papers"],
            "신입 개발자 취업": ["junior_jobs", "internships"],
        }
        assert profile["raw_onboarding_json"]["source_hints"] == ["https://newsletter.example", "@official"]
        assert set(profile["interest_types_json"]) == {"오픈소스", "연구논문", "신입 채용", "인턴"}
        assert [item["keyword"] for item in result["interest_graph"]] == ["AI", "신입 개발자 취업"]
    finally:
        directory.cleanup()


def test_type_choice_refines_route_without_restoring_unrelated_fallbacks():
    profile = {"raw_onboarding_json": {"interest_type_preferences": {"AI": ["ai_open_source", "research_papers"]}}}
    categories = SourceRouter().classify_interests(profile, [{"keyword": "AI", "status": "active"}])
    assert "AI_OPEN_SOURCE" in categories
    assert "RESEARCH" in categories
    assert "AI_TREND" not in categories
    # A research choice stays in a waiting state when OpenAlex has not been
    # explicitly activated; GitHub/HN do not become a substitute.
    support = collection_support("AI", ("github", "hackernews"), profile=profile)
    assert support["status"] == "awaiting_approved_source"
    assert support["sources"] == []


def test_broad_ai_offers_all_reader_facing_types_but_a_choice_constrains_routing():
    from src.sources.information_types import options_for_categories

    option_ids = {item["id"] for item in options_for_categories({"AI_TREND": 1})}
    assert {"ai_industry_news", "ai_product_updates", "ai_open_source", "research_papers"} <= option_ids
    profile = {"raw_onboarding_json": {"interest_type_preferences": {"AI": ["ai_product_updates"]}}}
    categories = SourceRouter().classify_interests(profile, [{"keyword": "AI", "status": "active"}])
    assert set(categories) == {"AI_TREND"}


def test_preview_is_read_only_and_returns_options_and_honest_availability():
    directory, store = _store()
    try:
        app = FastAPI()
        app.include_router(profile_router, prefix="/api/v1")
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=1)
        with TestClient(app) as client:
            before = store.get_profile(user_id=1)
            response = client.post("/api/v1/onboarding/preview", json={
                "keywords": ["AI", "청년 주거", "알 수 없는 주제"],
                "interest_type_preferences": {"AI": ["ai_product_updates"]},
            })
            assert response.status_code == 200
            items = {item["keyword"]: item for item in response.json()["interests"]}
            assert any(option["id"] == "ai_product_updates" for option in items["AI"]["information_type_options"])
            assert items["청년 주거"]["availability"]["state"] in {"permission_review", "source_setup_pending", "no_compatible_source"}
            assert items["청년 주거"]["availability"]["can_generate_initial_briefing"] is False
            assert items["알 수 없는 주제"]["availability"]["state"] == "no_compatible_source"
            assert items["알 수 없는 주제"]["availability"]["can_generate_initial_briefing"] is False
            assert store.get_profile(user_id=1) == before
    finally:
        directory.cleanup()

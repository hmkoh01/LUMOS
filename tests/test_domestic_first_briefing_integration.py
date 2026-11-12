from unittest.mock import patch

from src.engine.collection.source_support import collection_support, first_briefing_candidate_state
from src.engine.llm.domestic_preview import evaluate_personalised_item
from src.sources.router import SourceRouter


def _categories(keyword: str, type_id: str) -> set[str]:
    profile = {"raw_onboarding_json": {"interest_type_preferences": {keyword: [type_id]}}}
    return set(SourceRouter().classify_interests(profile, [{"keyword": keyword, "status": "active"}]))


def test_onboarding_type_to_route_to_card_evaluation_is_consistent_without_live_sources():
    cases = [
        ("technology startup", "technology_startup_support", "STARTUP_PROGRAM"),
        ("small business support", "small_business_support", "STARTUP_PROGRAM"),
        ("digital commerce", "digital_commerce_support", "STARTUP_PROGRAM"),
        ("junior developer hiring", "junior_jobs", "CAREER"),
        ("local cultural event", "local_events", "CULTURE_TRAVEL_EVENT"),
    ]
    for keyword, type_id, expected_category in cases:
        assert _categories(keyword, type_id) == {expected_category}
        profile = {"raw_onboarding_json": {"interest_type_preferences": {keyword: [type_id]}}}
        support = collection_support(keyword, ("mss_support_program", "public_institution_jobs", "tourapi"), profile=profile)
        # Permission-review sources may have isolated fixtures, but cannot
        # appear as a user's actual first-briefing candidate.
        assert first_briefing_candidate_state(support, 5) == "no_operational_source"


def test_selected_domestic_support_type_reaches_card_gate_without_leaking_to_technology_startup():
    digital = {
        "title": "Digital commerce programme",
        "url": "https://official.example/programme",
        "metrics_json": {
            "content_kind": "startup_program", "purpose": "online sales support",
            "support_target": "small businesses", "support_type": "digital commerce",
        },
    }
    technical = {
        "title": "Technology startup commercialisation programme",
        "url": "https://official.example/programme-tech",
        "metrics_json": {
            "content_kind": "startup_program", "purpose": "technology startup commercialisation",
            "support_target": "early startup", "support_type": "technology startup",
        },
    }
    job = {
        "title": "Backend developer junior hiring",
        "url": "https://official.example/job",
        "metrics_json": {"content_kind": "public_institution_job", "job_classification": "software development"},
    }
    event = {
        "title": "Seoul local festival", "url": "https://official.example/event",
        "metrics_json": {"content_kind": "culture_event", "event_status": "upcoming", "region": "Seoul", "genre": "festival"},
    }
    with patch("src.engine.llm.domestic_preview.matches_interest", return_value=True):
        assert evaluate_personalised_item(digital, "support", selected_information_types=("digital_commerce_support",))["eligible"] == "true"
        assert evaluate_personalised_item(digital, "support", selected_information_types=("technology_startup_support",))["reason"] == "support_information_type_mismatch"
        assert evaluate_personalised_item(technical, "support", selected_information_types=("technology_startup_support",))["eligible"] == "true"
        assert evaluate_personalised_item(job, "junior developer") ["eligible"] == "true"
    assert evaluate_personalised_item(event, "Seoul festival", preferred_region="Seoul")["eligible"] == "true"

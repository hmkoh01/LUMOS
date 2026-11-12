from datetime import date
from unittest.mock import patch

import pytest

from src.engine.config import EngineConfig
from src.engine.llm.handlers import make_generate_briefing_handler
from src.engine.llm.metadata_cards import build_metadata_cards, metadata_publish_allowed
from src.engine.llm.publisher import publish_metadata_pilot_cards
from src.engine.models import RawCandidate, ScoredCandidate
from src.storage.sqlite_store import SQLiteStore


def _tour(key="tour-1", region="Seoul", status="upcoming", url="https://visit.example/event"):
    return ScoredCandidate(candidate=RawCandidate(
        dedupe_key=key, source="tourapi", url=url, title=f"{region} Festival",
        published_at=date.today().isoformat(),
        metrics={"content_kind": "culture_event", "event_status": status,
                 "event_start_at": "2026-11-12", "event_end_at": "2026-11-14",
                 "region": region, "venue": f"{region} Hall", "genre": "festival"},
    ), importance_score=0.9)


def _dart(key="dart-1", company="Example Corp", url="https://dart.example/1"):
    return ScoredCandidate(candidate=RawCandidate(
        dedupe_key=key, source="opendart", url=url, author=company, title="Annual filing",
        published_at=date.today().isoformat(),
        metrics={"content_kind": "corporate_disclosure", "receipt_at": "2026-11-09"},
    ), importance_score=0.8)


def _public_intern_job(key="job-1", *, url="https://jobs.example/1", region="Seoul", job_type="Intern"):
    return ScoredCandidate(candidate=RawCandidate(
        dedupe_key=key, source="public_institution_jobs", url=url, author="Public Agency",
        title="Data analysis internship", published_at="2026-11-11",
        metrics={"content_kind": "public_institution_job", "announcement_start_at": "2026-11-11",
                 "job_type": job_type, "job_classification": "Data analysis", "region": region,
                 "recruitment_type": "Internship", "application_window_status": "unknown"},
    ), importance_score=0.7)


def test_metadata_cards_are_deterministic_and_filter_region_company_status_and_links():
    with patch("src.signals.translation.translate", side_effect=AssertionError("translation must not run")):
        cards, counts = build_metadata_cards([_tour(), _tour("busan", "Busan")], ["Seoul festival"], set(), set(), display_limit=5)
    assert counts == {"seen": 2, "eligible": 1, "withheld": 1}
    assert cards[0]["briefing"].generated_by.value == "rule"
    assert "Seoul Festival" in cards[0]["briefing"].display_title_ko
    assert build_metadata_cards([_tour(status="ended")], ["Seoul festival"], set(), set(), display_limit=5)[0] == []
    assert build_metadata_cards([_tour(url="")], ["Seoul festival"], set(), set(), display_limit=5)[0] == []
    duplicate_cards, duplicate_counts = build_metadata_cards([_tour(), _tour()], ["Seoul festival"], set(), set(), display_limit=5)
    assert len(duplicate_cards) == 1
    assert duplicate_counts == {"seen": 2, "eligible": 1, "withheld": 1}
    assert len(build_metadata_cards([_dart()], ["Example Corp"], set(), set(), display_limit=5)[0]) == 1
    assert build_metadata_cards([_dart()], ["economy"], set(), set(), display_limit=5)[0] == []
    intern_cards, _ = build_metadata_cards([_public_intern_job()], ["\uc778\ud134 \ucc44\uc6a9"], set(), set(), display_limit=5)
    assert len(intern_cards) == 1
    assert "\ub9c8\uac10\uc77c" not in intern_cards[0]["briefing"].display_title_ko
    assert any("\uc2e4\uc81c \uc811\uc218 \ub9c8\uac10\uc77c" in fact for fact in intern_cards[0]["briefing"].key_facts_ko)
    assert build_metadata_cards([_public_intern_job()], ["AI \uc0b0\uc5c5 \ub274\uc2a4"], set(), set(), display_limit=5)[0] == []
    assert build_metadata_cards([_public_intern_job(url="")], ["\uc778\ud134"], set(), set(), display_limit=5)[0] == []
    assert build_metadata_cards([_public_intern_job(region="", job_type="")], ["\uc778\ud134"], set(), set(), display_limit=5)[0] == []


def test_metadata_cards_support_korean_region_interest_without_translation():
    cards, _ = build_metadata_cards([_tour()], ["\uc11c\uc6b8 \ucd95\uc81c"], set(), set(), display_limit=1)
    assert len(cards) == 1
    assert "\ud589\uc0ac \uc77c\uc815" in cards[0]["briefing"].headline_summary_ko


def test_permission_review_sources_are_preview_only_not_publishable():
    assert metadata_publish_allowed("tourapi", {"metadata_card_publish_approved": True}) is False
    assert metadata_publish_allowed("opendart", {"metadata_card_publish_approved": True}) is False


def test_opendart_single_user_pilot_is_metadata_only_and_cannot_be_copied_to_another_user():
    config = {
        "pilot_mode": "single_user_metadata_only",
        "pilot_user_id": 454,
        "pilot_approval_reference": "local-owner-approval-2026-11-10",
        "metadata_card_publish_approved": True,
    }
    assert metadata_publish_allowed("opendart", config, user_id=454) is True
    assert metadata_publish_allowed("opendart", config, user_id=1) is False


def test_verified_company_alias_preserves_user_interest_without_fuzzy_matching():
    cards, _ = build_metadata_cards(
        [_dart(company="Official Company")], ["User Alias"], set(), set(), display_limit=1,
        verified_company_aliases={"User Alias": "Official Company"},
    )
    assert len(cards) == 1
    assert "User Alias" in cards[0]["recommendation_reason_ko"]
    assert build_metadata_cards(
        [_dart(company="Official Company")], ["User Alias"], set(), set(), display_limit=1,
        verified_company_aliases={"Different Alias": "Official Company"},
    )[0] == []


def test_handler_publishes_approved_metadata_card_without_calling_llm(tmp_path):
    store = SQLiteStore(tmp_path / "cards.sqlite")
    store.upsert_source_config("tourapi", enabled=True, user_id=1)
    run_id = store.create_pipeline_run("engine_v2", triggered_by="test", user_id=1)

    class ExplodingService:
        def build_cards(self, *_args, **_kwargs):  # pragma: no cover - failure proves isolation
            raise AssertionError("metadata source reached LLM service")

    payload = {
        "user_id": 1, "pipeline_run_id": run_id, "period": "daily", "role": "",
        "interests": ["Seoul festival"], "display_limit": 1,
        "candidates": [{
            "dedupe_key": "tour-1", "source": "tourapi", "url": "https://visit.example/event",
            "title": "Seoul Festival", "published_at": date.today().isoformat(),
            "metrics": {"content_kind": "culture_event", "event_status": "upcoming", "event_start_at": "2026-11-12", "event_end_at": "2026-11-14", "region": "Seoul", "venue": "Seoul Hall", "genre": "festival"},
        }],
    }
    with patch("src.engine.llm.handlers.metadata_publish_allowed", return_value=True), \
         patch("src.signals.translation.translate", side_effect=AssertionError("translation must not run")):
        result = make_generate_briefing_handler(ExplodingService(), store)(payload, EngineConfig())
    assert result["created"] == 1
    assert result["metadata_published_candidate_count"] == 1
    signal = store.get_today_active_signals(user_id=1)[0]
    assert signal["metadata_json"]["briefing_provider"] == "engine-v2-structured"
    assert signal["metadata_json"]["display_title_ko"]


@pytest.mark.parametrize(
    ("candidate", "interests", "expected"),
    [
        (_tour(region="Seoul").candidate, ["Seoul festival"], 1),
        (_tour(region="Busan").candidate, ["Busan festival"], 1),
        (_dart(company="Example Corp").candidate, ["Example Corp"], 1),
        (_dart(company="Example Corp").candidate, ["economy"], 0),
        (_tour(region="Seoul").candidate, ["Busan festival"], 0),
    ],
)
def test_metadata_only_handler_personalizes_without_llm_or_translation(tmp_path, candidate, interests, expected):
    """The Engine handler must never send metadata-only candidates to service.build_cards."""
    store = SQLiteStore(tmp_path / f"{candidate.source}-{expected}.sqlite")
    store.upsert_source_config(candidate.source, enabled=True, user_id=1)
    run_id = store.create_pipeline_run("engine_v2", triggered_by="test", user_id=1)

    class ExplodingService:
        def build_cards(self, *_args, **_kwargs):
            raise AssertionError("metadata candidate entered EngineBriefingService")

    payload = {
        "user_id": 1, "pipeline_run_id": run_id, "period": "daily", "role": "",
        "interests": interests, "display_limit": 1,
        "candidates": [{
            "dedupe_key": candidate.dedupe_key, "source": candidate.source, "url": candidate.url,
            "title": candidate.title, "author": candidate.author, "published_at": candidate.published_at,
            "metrics": candidate.metrics,
        }],
    }
    with patch("src.engine.llm.handlers.metadata_publish_allowed", return_value=True), \
         patch("src.signals.translation.translate", side_effect=AssertionError("translation must not run")):
        result = make_generate_briefing_handler(ExplodingService(), store)(payload, EngineConfig())
    assert result["created"] == expected
    assert result["generation_candidate_count"] == 0
    assert result["metadata_published_candidate_count"] == expected


def test_permission_review_candidate_is_withheld_and_never_falls_back_to_llm(tmp_path):
    store = SQLiteStore(tmp_path / "blocked.sqlite")
    store.upsert_source_config("tourapi", enabled=True, user_id=1)
    run_id = store.create_pipeline_run("engine_v2", triggered_by="test", user_id=1)

    class ExplodingService:
        def build_cards(self, *_args, **_kwargs):
            raise AssertionError("blocked metadata candidate entered EngineBriefingService")

    candidate = _tour().candidate
    payload = {
        "user_id": 1, "pipeline_run_id": run_id, "period": "daily", "role": "",
        "interests": ["Seoul festival"], "display_limit": 1,
        "candidates": [{
            "dedupe_key": candidate.dedupe_key, "source": candidate.source, "url": candidate.url,
            "title": candidate.title, "published_at": candidate.published_at, "metrics": candidate.metrics,
        }],
    }
    with patch("src.signals.translation.translate", side_effect=AssertionError("translation must not run")):
        result = make_generate_briefing_handler(ExplodingService(), store)(payload, EngineConfig())
    assert result["created"] == 0
    assert result["metadata_candidate_count"] == 1
    assert result["metadata_withheld_candidate_count"] == 1
    assert store.get_today_active_signals(user_id=1) == []


def test_permission_review_public_job_is_withheld_and_never_sent_to_llm(tmp_path):
    store = SQLiteStore(tmp_path / "public-job-blocked.sqlite")
    store.upsert_source_config("public_institution_jobs", enabled=True, user_id=1)
    run_id = store.create_pipeline_run("engine_v2", triggered_by="test", user_id=1)

    class ExplodingService:
        def build_cards(self, *_args, **_kwargs):
            raise AssertionError("public-job metadata candidate entered LLM service")

    candidate = _public_intern_job().candidate
    payload = {
        "user_id": 1, "pipeline_run_id": run_id, "period": "daily", "role": "",
        "interests": ["\uc778\ud134 \ucc44\uc6a9"], "display_limit": 1,
        "candidates": [{
            "dedupe_key": candidate.dedupe_key, "source": candidate.source, "url": candidate.url,
            "title": candidate.title, "author": candidate.author, "published_at": candidate.published_at,
            "metrics": candidate.metrics,
        }],
    }
    result = make_generate_briefing_handler(ExplodingService(), store)(payload, EngineConfig())
    assert result["created"] == 0
    assert result["metadata_candidate_count"] == 1
    assert result["metadata_withheld_candidate_count"] == 1


def test_metadata_pilot_publisher_appends_without_archiving_existing_engine_cards(tmp_path):
    store = SQLiteStore(tmp_path / "pilot-append.sqlite")
    existing_run = store.create_pipeline_run("engine_v2", triggered_by="test", user_id=454)
    existing_signal = {
        "dedupe_key": "engine-v2:daily:existing", "signal_date": date.today().isoformat(),
        "title": "Existing card", "summary": "Existing", "why_it_matters": "Existing",
        "recommended_action": "Open", "category": "engine-v2", "source_name": "github",
        "source_url": "https://example.test/existing", "source_items_json": [],
        "metadata_json": {"briefing_provider": "engine-v2-structured", "engine_period": "daily"},
            "confidence": 0.8, "rank": 1, "status": "active",
        }
    with store.connect() as conn:
        store._insert_signal(conn, existing_signal, existing_run, 454)
        conn.commit()
    pilot_run = store.create_pipeline_run("engine_v2_opendart_pilot", triggered_by="pilot", user_id=454)
    cards, _ = build_metadata_cards([_dart()], ["Example Corp"], set(), set(), display_limit=1)
    outcome = publish_metadata_pilot_cards(store, cards, user_id=454, pipeline_run_id=pilot_run)
    assert outcome == {"created": 1, "retained": 0, "archived": 0, "reserve_count": 0}
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT source_name FROM signals WHERE user_id = ? AND status = 'active'", (454,)
        ).fetchall()
    assert {row["source_name"] for row in rows} == {"github", "opendart"}

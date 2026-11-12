from datetime import datetime, timezone

import pytest

from src.engine.queue.sqlite_store import SQLiteQueueStore
from src.engine.config import EngineConfig, CollectionConfig
from src.engine.operations import EngineOperations
from src.sources.source_discovery import (
    DisabledWebDiscoveryProvider,
    OfficialDirectoryProvider,
    SourceDiscoveryBacklog,
    candidate_can_route,
    configured_discovery_provider,
    verified_official_directory_provider,
)


def test_official_seeds_are_non_operational_and_do_not_store_credentials(tmp_path):
    queue = SQLiteQueueStore(tmp_path / "shared.sqlite")
    rows = SourceDiscoveryBacklog(queue).seed_official_candidates()
    by_id = {row["source_id"]: row for row in rows}
    assert by_id["employment24"]["candidate_status"] == "requires_registration"
    assert by_id["employment24"]["adapter_status"] == "implemented"
    assert by_id["employment24"]["discovery_origin"] == "seed"
    infrastructure = queue.list_source_discovery_backlog(entry_kind="discovery_infrastructure")
    assert [row["source_id"] for row in infrastructure] == ["data_go_kr_catalogue_api"]
    assert infrastructure[0]["candidate_status"] == "requires_registration"
    assert infrastructure[0]["capabilities"]["live_query_count"] == 0
    assert candidate_can_route(infrastructure[0]) is False
    assert by_id["msit_press_rss"]["candidate_status"] == "permission_review"
    assert {row["source_id"] for row in rows} >= {
        "employment24", "msit_press_rss", "openai_news_rss", "google_official_blog_rss",
        "public_institution_jobs", "msit_announcements",
    }
    with pytest.raises(ValueError, match="credentials"):
        queue.upsert_source_discovery_candidate({
            "source_id": "unsafe", "domain": "example.test", "official_url": "https://example.test",
            "capabilities": {"api_key": "must-not-be-stored"},
        })
    with pytest.raises(ValueError, match="credentials"):
        queue.upsert_source_discovery_candidate({
            "source_id": "unsafe-url", "domain": "example.test",
            "official_url": "https://example.test/?serviceKey=must-not-be-stored",
        })


def test_demand_is_aggregated_once_per_category_window_and_shared_across_workers(tmp_path):
    path = tmp_path / "shared.sqlite"
    one, two = SQLiteQueueStore(path), SQLiteQueueStore(path)
    backlog = SourceDiscoveryBacklog(one, window_days=7)
    first = backlog.record_missing_categories({"CAREER": 3}, observed_at=datetime(2026, 11, 11, tzinfo=timezone.utc))
    second = SourceDiscoveryBacklog(two, window_days=7).record_missing_categories(
        {"CAREER": 99}, observed_at=datetime(2026, 11, 11, tzinfo=timezone.utc)
    )
    assert set(first) == {"employment24", "public_institution_jobs"}
    assert second == []
    row = next(item for item in one.list_source_discovery_backlog() if item["source_id"] == "employment24")
    assert row["demand_count"] == 3


def test_only_one_worker_can_lease_a_discovered_candidate(tmp_path):
    path = tmp_path / "shared.sqlite"
    one, two = SQLiteQueueStore(path), SQLiteQueueStore(path)
    one.upsert_source_discovery_candidate({
        "source_id": "official_candidate", "domain": "example.test", "official_url": "https://example.test",
        "candidate_status": "discovered", "adapter_status": "adapter_needed",
    })
    assert one.claim_source_discovery_candidate("official_candidate", "worker-a") is True
    assert two.claim_source_discovery_candidate("official_candidate", "worker-b") is False


def test_disabled_provider_never_performs_a_search_or_consumes_budget(tmp_path):
    queue = SQLiteQueueStore(tmp_path / "queue.sqlite")
    backlog = SourceDiscoveryBacklog(queue, provider=DisabledWebDiscoveryProvider(), max_requests_per_day=5)
    assert backlog.execute_discovery({"category": "CAREER"}) == {"status": "provider_disabled", "stored_candidates": 0}
    assert queue.get_source_request_usage("source_discovery", datetime.now(timezone.utc).date().isoformat()) == 0


def test_unapproved_discovery_infrastructure_does_not_block_demand_or_existing_candidates(tmp_path):
    queue = SQLiteQueueStore(tmp_path / "queue.sqlite")
    backlog = SourceDiscoveryBacklog(queue)
    backlog.record_missing_categories({"CAREER": 2}, observed_at=datetime(2026, 11, 11, tzinfo=timezone.utc))
    career = queue.list_source_discovery_backlog(entry_kind="source_candidate", registration_required=True)
    assert {row["source_id"] for row in career} >= {"employment24", "public_institution_jobs"}
    infrastructure = queue.list_source_discovery_backlog(entry_kind="discovery_infrastructure")
    assert infrastructure[0]["capabilities"]["approved_for_automatic_access"] is False


def test_key_or_schema_alone_never_enables_routing():
    candidate = {
        "candidate_status": "approved", "adapter_status": "implemented",
        "capabilities": {"activation_checks": {"credentials_verified": True, "schema_verified": True,
                                                     "license_verified": False, "canary_passed": False,
                                                     "operator_approved": False}},
    }
    assert candidate_can_route(candidate) is False
    candidate["candidate_status"] = "enabled"
    candidate["capabilities"]["activation_checks"].update({"license_verified": True, "canary_passed": True, "operator_approved": True})
    assert candidate_can_route(candidate) is True


def test_same_subject_is_counted_once_but_two_subjects_are_aggregated_without_ids(tmp_path):
    queue = SQLiteQueueStore(tmp_path / "queue.sqlite")
    backlog = SourceDiscoveryBacklog(queue)
    when = datetime(2026, 11, 11, tzinfo=timezone.utc)
    window = backlog.window_key(when)
    tokens = {
        "CAREER": [
            backlog.subject_digest("CAREER", window, 101),
            backlog.subject_digest("CAREER", window, 102),
            backlog.subject_digest("CAREER", window, 101),
        ]
    }
    backlog.record_missing_categories({"CAREER": 2}, observed_at=when, subject_tokens_by_category=tokens)
    backlog.record_missing_categories({"CAREER": 2}, observed_at=when, subject_tokens_by_category=tokens)
    for row in queue.list_source_discovery_backlog(registration_required=True):
        if "CAREER" in row["categories"]:
            assert row["demand_count"] == 2


def test_approved_directory_provider_is_budgeted_and_stores_only_official_metadata(tmp_path):
    queue = SQLiteQueueStore(tmp_path / "queue.sqlite")
    provider = OfficialDirectoryProvider([{
        "source_id": "official-directory-record", "domain": "official.example",
        "official_url": "https://official.example/api", "documentation_url": "https://official.example/docs",
        "categories": ["CAREER"], "candidate_status": "adapter_needed", "adapter_status": "adapter_needed",
    }])
    backlog = SourceDiscoveryBacklog(queue, provider=provider, max_requests_per_day=1)
    assert backlog.execute_discovery({"category": "CAREER"}) == {"status": "completed", "stored_candidates": 1}
    assert backlog.execute_discovery({"category": "CAREER"}) == {"status": "budget_exhausted", "stored_candidates": 0}
    row = next(row for row in queue.list_source_discovery_backlog() if row["source_id"] == "official-directory-record")
    assert row["official_url"] == "https://official.example/api"


def test_verified_official_directory_discovers_a_new_candidate_in_a_temporary_backlog(tmp_path):
    """The provider stores reviewed official metadata, not a search response."""
    queue = SQLiteQueueStore(tmp_path / "queue.sqlite")
    backlog = SourceDiscoveryBacklog(queue, provider=verified_official_directory_provider(), max_requests_per_day=1)

    result = backlog.execute_discovery({"category": "CAREER"})

    assert result == {"status": "completed", "stored_candidates": 1}
    candidate = next(row for row in queue.list_source_discovery_backlog() if row["source_id"] == "public_service_jobs")
    assert candidate["categories"] == ["CAREER"]
    assert candidate["registration_required"] is True
    assert candidate["provider_name"] == "인사혁신처"
    assert candidate["registration_url"] == "https://www.data.go.kr/data/15156780/openapi.do"
    assert candidate["candidate_status"] == "adapter_needed"
    assert candidate["adapter_status"] == "schema_pending"
    assert candidate["discovery_origin"] == "official_directory_catalogue"
    assert candidate_can_route(candidate) is False
    assert "servicekey=" not in repr(candidate).casefold()
    assert "authorization" not in repr(candidate).casefold()
    assert backlog.execute_discovery({"category": "CAREER"}) == {"status": "budget_exhausted", "stored_candidates": 0}


def test_official_directory_is_disabled_unless_explicitly_configured(tmp_path):
    queue = SQLiteQueueStore(tmp_path / "queue.sqlite")
    disabled = SourceDiscoveryBacklog(queue, provider=configured_discovery_provider(official_directory_enabled=False), max_requests_per_day=1)
    assert disabled.execute_discovery({"category": "CAREER"}) == {"status": "provider_disabled", "stored_candidates": 0}
    enabled = SourceDiscoveryBacklog(queue, provider=configured_discovery_provider(official_directory_enabled=True), max_requests_per_day=1)
    assert enabled.execute_discovery({"category": "CAREER"}) == {"status": "completed", "stored_candidates": 1}


def test_engine_handler_uses_official_directory_only_with_explicit_opt_in(tmp_path):
    queue = SQLiteQueueStore(tmp_path / "queue.sqlite")
    operations = object.__new__(EngineOperations)
    operations.queue = queue
    operations.config = EngineConfig(
        enabled=True,
        collection=CollectionConfig(
            source_discovery_enabled=True,
            source_discovery_official_directory_enabled=True,
            source_discovery_max_requests_per_day=1,
        ),
    )
    assert operations._source_discovery_handler({"category": "CAREER"}, operations.config) == {
        "status": "completed", "stored_candidates": 1
    }
    discovered = next(row for row in queue.list_source_discovery_backlog() if row["source_id"] == "public_service_jobs")
    assert candidate_can_route(discovered) is False


def test_operator_backlog_view_exposes_only_candidate_metadata(tmp_path, monkeypatch):
    """Exercise the operator handler without opening a web server or socket."""
    from src.api import source_discovery_admin as admin

    path = tmp_path / "queue.sqlite"
    queue = SQLiteQueueStore(path)
    backlog = SourceDiscoveryBacklog(queue, provider=verified_official_directory_provider(), max_requests_per_day=1)
    backlog.seed_official_candidates()
    backlog.execute_discovery({"category": "CAREER"})
    monkeypatch.setattr(admin, "queue_path", lambda: path)
    monkeypatch.setenv("LUMOS_SOURCE_DISCOVERY_ADMIN_TOKEN", "test-operator-token")
    admin._require_operator("test-operator-token")

    response = admin.get_source_discovery_backlog(adapter_needed=True)

    assert response["success"] is True
    assert [candidate["source_id"] for candidate in response["candidates"]] == ["public_service_jobs"]
    candidate = response["candidates"][0]
    assert candidate["registration_required"] is True
    assert candidate["provider_name"] == "인사혁신처"
    assert candidate["routing_eligible"] is False
    assert candidate["discovery_origin"] == "official_directory_catalogue"
    assert "serviceKey" not in repr(candidate)

    infrastructure = admin.get_source_discovery_backlog(entry_kind="discovery_infrastructure")
    assert [candidate["source_id"] for candidate in infrastructure["candidates"]] == ["data_go_kr_catalogue_api"]
    assert infrastructure["candidates"][0]["routing_eligible"] is False


def test_unknown_gap_creates_one_deduped_background_job_without_user_data(tmp_path):
    queue = SQLiteQueueStore(tmp_path / "queue.sqlite")
    backlog = SourceDiscoveryBacklog(queue)
    backlog.record_missing_categories({"UNSUPPORTED_CATEGORY": 4}, observed_at=datetime(2026, 11, 11, tzinfo=timezone.utc))
    backlog.record_missing_categories({"UNSUPPORTED_CATEGORY": 4}, observed_at=datetime(2026, 11, 11, tzinfo=timezone.utc))
    jobs = queue.list_jobs(job_type="source_discovery")
    assert len(jobs) == 1
    assert jobs[0].payload_json == {"category": "UNSUPPORTED_CATEGORY", "window": "2026-11-11-w45"}


def test_operations_aggregates_missing_interest_demand_without_persisting_user_ids(tmp_path, monkeypatch):
    class Store:
        def get_profile(self, *, user_id): return {"raw_onboarding_json": {}}
        def get_enabled_source_configs(self, *, user_id): return []
    operations = object.__new__(EngineOperations)
    operations.store, operations.queue = Store(), SQLiteQueueStore(tmp_path / "queue.sqlite")
    operations.config = EngineConfig(enabled=True, collection=CollectionConfig(source_discovery_enabled=True))
    monkeypatch.setattr("src.engine.operations.collection_support", lambda *_args, **_kwargs: {"status": "awaiting_approved_source"})
    operations._record_source_discovery_gaps([
        {"user_id": 1, "keyword": "인턴", "weight": 1.0},
        {"user_id": 2, "keyword": "인턴", "weight": 1.0},
    ], [])
    career = next(row for row in operations.queue.list_source_discovery_backlog() if row["source_id"] == "employment24")
    assert career["demand_count"] == 2
    assert "user_id" not in career

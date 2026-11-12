"""Offline coverage for durable generate-job/run lifecycle alignment."""

from datetime import datetime

from src.context.onboarding import OnboardingService
from src.engine.config import CollectionConfig, EngineConfig
from src.engine.collection.source_support import collection_support
from src.engine.operations import EngineOperations, KST
from src.storage.sqlite_store import SQLiteStore


def _operations(tmp_path, monkeypatch):
    queue_path = tmp_path / "queue.sqlite"
    monkeypatch.setattr("src.engine.operations.queue_path", lambda: queue_path)
    store = SQLiteStore(tmp_path / "app.sqlite")
    # ``python`` is developer-technology intent, so the existing GitHub
    # pilot is a legitimate source for this focused queue lifecycle test.
    # Broad AI trend intent intentionally does not route to GitHub.
    OnboardingService(store).save({"keywords": ["python"]}, user_id=1)
    store.upsert_source_config("github", enabled=True, user_id=1)
    return store, EngineOperations(store, EngineConfig(enabled=True))


def _runs(store):
    return store.get_recent_pipeline_runs(limit=20, user_id=1)


def test_same_cycle_reuses_generate_jobs_without_creating_orphan_runs(tmp_path, monkeypatch):
    store, operations = _operations(tmp_path, monkeypatch)
    operations._enqueue_user_periods(1, "2026-11-11-1830")
    first_runs = _runs(store)
    assert len(first_runs) == 3
    assert {run["status"] for run in first_runs} == {"running"}

    # Both pending and completed durable jobs suppress the same snapshot.
    operations._enqueue_user_periods(1, "2026-11-11-1830")
    assert len(_runs(store)) == 3
    for job in operations.queue.list_jobs(limit=10):
        operations.queue.complete(job.id, {"fixture": True})
    operations._enqueue_user_periods(1, "2026-11-11-1830")
    assert len(_runs(store)) == 3


def test_interest_snapshot_change_gets_a_new_generate_key(tmp_path, monkeypatch):
    store, operations = _operations(tmp_path, monkeypatch)
    operations._enqueue_user_periods(1, "2026-11-11-1830")
    OnboardingService(store).save({"keywords": ["AI", "데이터"]}, user_id=1)
    # Use an ASCII snapshot change here; this test exercises the dedupe-key
    # contract rather than Unicode handling.
    OnboardingService(store).save({"keywords": ["python", "data"]}, user_id=1)
    operations._enqueue_user_periods(1, "2026-11-11-1830")
    assert len(_runs(store)) == 6
    assert len(operations.queue.list_jobs(limit=10)) == 6


def test_enqueue_race_marks_unexecuted_run_skipped_not_completed(tmp_path, monkeypatch):
    store, operations = _operations(tmp_path, monkeypatch)
    operations._enqueue_user_periods(1, "2026-11-11-1830")
    for job in operations.queue.list_jobs(limit=10):
        operations.queue.complete(job.id, {"fixture": True})

    # Simulate another worker inserting between the pre-check and enqueue.
    monkeypatch.setattr(operations.queue, "get_job_by_dedupe_key", lambda _key: None)
    operations._enqueue_user_periods(1, "2026-11-11-1830")
    runs = _runs(store)
    skipped = [run for run in runs if run["status"] == "skipped"]
    assert len(skipped) == 3
    assert all(run["summary_json"]["generation_state"] == "skipped_deduplicated" for run in skipped)
    assert all(run["summary_json"]["deduplicated_to_job_id"] for run in skipped)


def test_no_operational_source_creates_no_generate_run_or_llm_job(tmp_path, monkeypatch):
    queue_path = tmp_path / "queue.sqlite"
    monkeypatch.setattr("src.engine.operations.queue_path", lambda: queue_path)
    store = SQLiteStore(tmp_path / "app.sqlite")
    OnboardingService(store).save({
        "keywords": ["AI"],
        "interest_type_preferences": {"AI": ["ai_industry_news"]},
    }, user_id=890)
    operations = EngineOperations(store, EngineConfig(enabled=True))
    operations._enqueue_user_periods(890, "2026-11-11-1830")
    assert store.get_recent_pipeline_runs(limit=10, user_id=890) == []
    assert operations.queue.list_jobs(limit=10) == []


def test_opendart_metadata_pilot_does_not_enqueue_empty_generic_briefings(tmp_path, monkeypatch):
    """The append-only Pilot is not a generic LLM briefing source."""
    queue_path = tmp_path / "queue.sqlite"
    monkeypatch.setattr("src.engine.operations.queue_path", lambda: queue_path)
    store = SQLiteStore(tmp_path / "app.sqlite")
    OnboardingService(store).save({"keywords": ["Example Company"]}, user_id=454)
    store.upsert_source_config(
        "opendart", enabled=True, user_id=454,
        config={"pilot_mode": "single_user_metadata_only", "pilot_user_id": 454},
    )
    operations = EngineOperations(store, EngineConfig(enabled=True))
    # Routing itself is covered elsewhere; isolate the generic-generation
    # boundary so the test makes no environment or external-source assumption.
    monkeypatch.setattr(
        "src.engine.operations.collection_support",
        lambda *_args, **_kwargs: {"status": "supported", "sources": ["opendart"]},
    )

    operations._enqueue_user_periods(454, "2026-11-12-0630")

    assert store.get_recent_pipeline_runs(limit=10, user_id=454) == []
    assert operations.queue.list_jobs(limit=10) == []


def test_scheduled_plan_keeps_developer_collection_when_other_interest_is_approval_gated(tmp_path, monkeypatch):
    """An AI-industry choice must not suppress this user's Python plan."""
    queue_path = tmp_path / "queue.sqlite"
    monkeypatch.setattr("src.engine.operations.queue_path", lambda: queue_path)
    store = SQLiteStore(tmp_path / "app.sqlite")
    OnboardingService(store).save({
        "keywords": ["AI", "python"],
        "interest_type_preferences": {"AI": ["ai_industry_news"]},
        "information_type_preferences_configured": True,
    }, user_id=1)
    store.upsert_source_config("github", enabled=True, user_id=1)
    store.upsert_source_config("hackernews", enabled=True, user_id=1)
    config = EngineConfig(
        enabled=True,
        collection=CollectionConfig(
            scheduler_enabled=True,
            pilot_sources=("github", "hackernews"),
        ),
    )
    operations = EngineOperations(store, config)
    monkeypatch.setattr(store, "get_active_user_ids", lambda _window_days: [1])

    created = operations.run_due_slots(datetime(2026, 11, 12, 6, 30, tzinfo=KST))
    collect_sources = {
        job.payload_json["source"] for job in operations.queue.list_jobs(job_type="collect", limit=10)
    }
    assert created == 2
    assert collect_sources == {"github", "hackernews"}

    # A later catch-up pass reuses the exact KST cycle rather than creating
    # duplicate collection jobs.
    assert operations.run_due_slots(datetime(2026, 11, 12, 9, 6, tzinfo=KST)) == 0
    assert len(operations.queue.list_jobs(job_type="collect", limit=10)) == 2


def test_broad_content_interest_does_not_use_hackernews_as_a_fallback():
    result = collection_support(
        "marketing",
        ("hackernews", "github"),
        [{"source_id": "hackernews", "config_json": {}}, {"source_id": "github", "config_json": {}}],
        profile={},
    )
    assert result["sources"] == []
    assert result["status"] == "awaiting_approved_source"


def test_restart_does_not_add_new_collect_source_to_a_settled_cycle(tmp_path, monkeypatch):
    """A deployment waits for the next slot instead of backfilling new I/O."""
    queue_path = tmp_path / "queue.sqlite"
    monkeypatch.setattr("src.engine.operations.queue_path", lambda: queue_path)
    store = SQLiteStore(tmp_path / "app.sqlite")
    OnboardingService(store).save({"keywords": ["python"]}, user_id=1)
    store.upsert_source_config("github", enabled=True, user_id=1)
    store.upsert_source_config("hackernews", enabled=False, user_id=1)
    config = EngineConfig(enabled=True, collection=CollectionConfig(pilot_sources=("github", "hackernews")))
    operations = EngineOperations(store, config)
    cycle = "2026-11-12-0630"
    operations.plan_cycle(cycle, {1})
    finalizer = next(job for job in operations.queue.list_jobs(limit=10) if job.job_type == "prepare_briefings")
    operations.queue.complete(finalizer.id, {"fixture": True})

    # Hacker News becomes configured only after this cycle has settled.
    store.upsert_source_config("hackernews", enabled=True, user_id=1)
    operations.plan_cycle(cycle, {1})

    assert {
        job.payload_json["source"] for job in operations.queue.list_jobs(job_type="collect", limit=10)
    } == {"github"}
    # A fresh cycle remains free to collect from both approved sources.
    operations.plan_cycle("2026-11-12-1830", {1})
    assert {
        job.payload_json["source"] for job in operations.queue.list_jobs(job_type="collect", limit=20)
    } == {"github", "hackernews"}

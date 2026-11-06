from datetime import date, timedelta

from src.api.engine import _try_backfill_one
from src.api.engine import get_briefing
from src.engine.config import BudgetConfig, EngineConfig
from src.engine.llm.cache import BriefingCache
from src.engine.llm.handlers import make_generate_briefing_handler, make_generate_briefing_job, register_generate_briefing_handler
from src.engine.llm.providers import MockStructuredBriefingProvider
from src.engine.llm.service import EngineBriefingService
from src.engine.llm.structured_cache import StructuredBriefingCache
from src.engine.models import Job, JobType
from src.engine.queue.sqlite_store import SQLiteQueueStore
from src.engine.queue.worker import WorkerPool
from src.storage.sqlite_store import SQLiteStore


def _candidate(key, title):
    return {
        "dedupe_key": key, "source": "github", "url": f"https://example.test/{key}",
        "title": title, "summary": f"{title} verified release notes",
        "published_at": date.today().isoformat(), "metrics": {},
    }


def _setup(tmp_path):
    store = SQLiteStore(tmp_path / "app.sqlite")
    store.upsert_source_config("github", enabled=True, user_id=1)
    service = EngineBriefingService(
        MockStructuredBriefingProvider(), BriefingCache(tmp_path / "briefings.sqlite"),
        StructuredBriefingCache(tmp_path / "structured.sqlite"),
    )
    config = EngineConfig(enabled=True, external_calls_allowed=False, budget=BudgetConfig(max_briefing_display_count=2))
    run_id = store.create_pipeline_run("engine_v2", triggered_by="test", user_id=1)
    payload = {
        "user_id": 1, "pipeline_run_id": run_id, "period": "daily", "role": "developer",
        "interests": ["LangGraph workflow", "AI agent development"], "display_limit": 2,
        "candidates": [
            _candidate("langgraph", "LangGraph workflow interrupt IDs"),
            _candidate("mcp", "MCP Python SDK tool update"),
            _candidate("agents", "AI agents SDK security update"),
            _candidate("off-topic", "PostgreSQL vacuum guide"),
        ],
    }
    return store, service, config, run_id, payload


def test_generate_briefing_worker_persists_cards_reserves_and_backfills(tmp_path):
    store, service, config, run_id, payload = _setup(tmp_path)
    queue = SQLiteQueueStore(tmp_path / "queue.sqlite")
    register_generate_briefing_handler(service, store)
    queue.enqueue(Job(job_type=JobType.GENERATE_BRIEFING, dedupe_key="briefing:u1:daily", payload_json=payload, max_retries=0))
    assert WorkerPool(queue, config).process_one()
    completed = queue.list_jobs(status="completed")[0]
    assert completed.result_json["created"] == 2
    assert completed.result_json["reserve_count"] == 1
    assert len(store.get_signals_for_period("today", user_id=1)) == 2
    response = get_briefing("daily", store, type("User", (), {"id": 1})(), config)
    assert response["success"] is True
    assert len(response["signals"]) == 2

    replacement = _try_backfill_one(store, 1)
    assert replacement is not None
    assert len(store.get_today_active_signals(user_id=1)) == 3

    # A duplicate delivery preserves existing cards and preferences.
    again = make_generate_briefing_handler(service, store)(payload, config)
    assert again["created"] == 0
    assert len(store.get_today_active_signals(user_id=1)) == 3


def test_generate_briefing_job_defaults_to_no_retry():
    job = make_generate_briefing_job(dedupe_key="briefing:u1:daily", payload={"user_id": 1})
    assert job.max_retries == 0


def test_official_technology_source_runs_full_fake_flow(tmp_path):
    store, service, config, run_id, _payload = _setup(tmp_path)
    store.upsert_source_config("official_openai_engineering", enabled=True, user_id=1)
    payload = {
        "user_id": 1, "pipeline_run_id": run_id, "period": "weekly", "role": "developer",
        "interests": ["Codex"], "display_limit": 1,
        "candidates": [{
            "dedupe_key": "openai-scaling-git", "source": "official_openai_engineering",
            "url": "https://openai.com/index/scaling-git-at-openai/", "title": "Scaling Git at OpenAI",
            "summary": "OpenAI describes Pando, a Git backend compatible with the Git protocol and client as Codex increases concurrent work.",
            "published_at": (date.today() - timedelta(days=1)).isoformat(), "metrics": {},
        }],
    }
    result = make_generate_briefing_handler(service, store)(payload, config)
    assert result["created"] == 1
    response = get_briefing("weekly", store, type("User", (), {"id": 1})(), config)
    assert response["success"] is True
    assert response["signals"][0]["title"] == "Scaling Git at OpenAI"


def test_users_share_content_cache_but_keep_stored_cards_isolated(tmp_path):
    store, service, config, _run_id, payload = _setup(tmp_path)
    handler = make_generate_briefing_handler(service, store)
    first = handler(payload, config)
    assert first["created"] == 2

    with store.connect() as conn:
        conn.execute("INSERT INTO users (id, external_id, display_name) VALUES (2, 'test-user-2', 'User 2')")
        conn.commit()
    store.upsert_source_config("github", enabled=True, user_id=2)
    second_run = store.create_pipeline_run("engine_v2", triggered_by="test", user_id=2)
    second_payload = {**payload, "user_id": 2, "pipeline_run_id": second_run,
                      "interests": ["AI agent development", "MCP tools"]}
    second = handler(second_payload, config)
    assert second["created"] == 2
    first_keys = {s["dedupe_key"] for s in store.get_today_active_signals(user_id=1)}
    second_keys = {s["dedupe_key"] for s in store.get_today_active_signals(user_id=2)}
    assert first_keys
    assert second_keys
    # Same source identity is allowed per user; rows are never shared.
    assert len(store.get_today_active_signals(user_id=1)) == 2
    assert len(store.get_today_active_signals(user_id=2)) == 2

"""One-shot, isolated Agent Platform Engine v2 staging check.

Never targets the application DB and never starts a scheduler or collector.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    load_dotenv(root / ".env", override=False)
    # Process-local staging permissions only; no project .env mutation.
    os.environ.update({
        "LUMOS_ENGINE_V2": "true", "LUMOS_EXTERNAL_CALLS": "true",
        "LUMOS_ENGINE_LLM": "approved", "LUMOS_ENGINE_LLM_PROVIDER": "agent_platform",
        "LUMOS_BLOCK_EXTERNAL_CALLS": "false", "LUMOS_ALLOW_ASSISTANT_LLM": "false",
        "LUMOS_GEMINI_EXPERIMENT": "", "LUMOS_TEST_MODE": "false",
    })
    from src.api.engine import get_briefing
    from src.engine.config import BudgetConfig, EngineConfig, LLMConfig
    from src.engine.llm.cache import BriefingCache
    from src.engine.llm.handlers import make_generate_briefing_handler
    from src.engine.llm.providers import AgentPlatformEngineProvider
    from src.engine.llm.service import EngineBriefingService
    from src.engine.llm.structured_cache import StructuredBriefingCache
    from src.storage.sqlite_store import SQLiteStore

    source = json.loads((root / "artifacts/gemini_briefing_experiment/sources.json").read_text(encoding="utf-8"))[0]
    with tempfile.TemporaryDirectory(prefix="lumos-engine-stage-") as temp:
        directory = Path(temp)
        store = SQLiteStore(directory / "stage.sqlite")
        store.upsert_source_config("github", enabled=True, user_id=1)
        config = EngineConfig(
            enabled=True, external_calls_allowed=True,
            llm=LLMConfig(provider="agent_platform", agent_platform_model="gemini-3.5-flash-lite"),
            budget=BudgetConfig(max_briefing_display_count=1),
        )
        provider = AgentPlatformEngineProvider(config)
        service = EngineBriefingService(provider, BriefingCache(directory / "cache.sqlite"), StructuredBriefingCache(directory / "cache.sqlite"))
        run_id = store.create_pipeline_run("engine_v2_staging", triggered_by="staging", user_id=1)
        payload = {
            "user_id": 1, "pipeline_run_id": run_id, "period": "weekly", "role": "developer",
            "interests": ["AI agent development", "LangGraph workflow", "execution interruption resume stability"],
            "display_limit": 1,
            "candidates": [{
                "dedupe_key": source["id"], "source": "github", "url": source["url"],
                "title": source["title"], "summary": source["summary"], "published_at": source["published_at"],
                "metrics": {},
            }],
        }
        result = make_generate_briefing_handler(service, store)(payload, config)
        api = get_briefing("weekly", store, type("User", (), {"id": 1})(), config)
        requests_after_first = len(provider.usage_events)
        again = make_generate_briefing_handler(service, store)(payload, config)
        report = {
            "staging_only": True, "scheduler_started": False, "collector_started": False,
            "first_result": result, "second_result": again,
            "api_signal_count": len(api["signals"]),
            "api_title": api["signals"][0].get("display_title_ko", "") if api["signals"] else "",
            "api_summary": api["signals"][0].get("headline_summary_ko", "") if api["signals"] else "",
            "api_reason": api["signals"][0].get("recommendation_reason_ko", "") if api["signals"] else "",
            "usage": provider.usage_events,
            "first_request_count": requests_after_first,
            "total_request_count": len(provider.usage_events),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        service.structured_cache.close()


if __name__ == "__main__":
    main()

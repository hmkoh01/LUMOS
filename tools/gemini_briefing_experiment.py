"""Isolated Agent Platform briefing experiment; dry run is the default."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACT_DIR = ROOT / "artifacts" / "gemini_briefing_experiment"
SOURCES_PATH = ARTIFACT_DIR / "sources.json"
RESULTS_PATH = ARTIFACT_DIR / "results.json"
BASELINE_MODEL = "gemini-3.5-flash-lite"
COMPARISON_MODEL = "gemini-3.8-flash"
OFFICIAL_OPENAI_ENGINEERING_SOURCE = {
    "id": "openai-scaling-git-2026-11-02",
    "source": "official_openai_engineering",
    "url": "https://openai.com/index/scaling-git-at-openai/",
    "title": "Scaling Git at OpenAI",
    "summary": "OpenAI describes Pando, a new backend for Git repositories that retains compatibility with the Git protocol and client as Codex increases concurrent work.",
    "published_at": "2026-11-02T00:00:00Z",
}
USD_TO_KRW_CONSERVATIVE = 1_600
LIMITS = {"sources": 10, "max_requests": 24, "max_concurrency": 1, "max_retries": 0,
          "content_input_tokens": 5_000, "personalization_input_tokens": 1_500,
          "content_output_tokens": 1024, "personalization_output_tokens": 768}
PRICING = {BASELINE_MODEL: {"input": 0.30, "output": 2.50},
           COMPARISON_MODEL: {"input": 0.75, "output": 3.75}}


def _estimate(model: str, content_calls: int, personalization_calls: int) -> Dict[str, Any]:
    prices = PRICING[model]
    input_tokens = content_calls * LIMITS["content_input_tokens"] + personalization_calls * LIMITS["personalization_input_tokens"]
    output_tokens = content_calls * LIMITS["content_output_tokens"] + personalization_calls * LIMITS["personalization_output_tokens"]
    thinking_tokens = output_tokens
    cost_usd = input_tokens * prices["input"] / 1_000_000 + (output_tokens + thinking_tokens) * prices["output"] / 1_000_000
    return {"model": model, "requests": content_calls + personalization_calls,
            "max_input_tokens": input_tokens, "max_output_tokens": output_tokens,
            "max_thinking_tokens": thinking_tokens, "max_cost_usd": round(cost_usd, 6),
            "max_cost_krw": round(cost_usd * USD_TO_KRW_CONSERVATIVE)}


def dry_run() -> Dict[str, Any]:
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    if len(sources) != LIMITS["sources"]:
        raise ValueError("experiment requires exactly 10 approved sources")
    if any(len(item["summary"]) > 3_500 for item in sources):
        raise ValueError("a source exceeds the dry-run input character cap")
    baseline = _estimate(BASELINE_MODEL, 10, 10)
    comparison = _estimate(COMPARISON_MODEL, 2, 2)
    total_krw = baseline["max_cost_krw"] + comparison["max_cost_krw"]
    return {"mode": "dry_run", "network_requests": 0, "sources": len(sources),
            "baseline": baseline, "comparison_cap": comparison,
            "total_request_cap": baseline["requests"] + comparison["requests"],
            "total_max_cost_krw": total_krw, "within_krw_3000_budget": total_krw <= 3_000,
            "limits": LIMITS, "grounding_tools": "disabled"}


def _safe_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Persist usage only; never persist credentials or raw provider errors."""
    return {key: metadata.get(key) for key in (
        "model", "model_version", "call_type", "retries", "error_code",
        "json_parse_failure_type", "finish_reason", "max_output_tokens",
        "validation_issues",
        "input_tokens", "output_tokens", "thinking_tokens", "latency_ms",
    )}


def _load_experiment_key() -> None:
    """Load only Agent Platform configuration into this short-lived process."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    allowed = {"GOOGLE_API_KEY", "GOOGLE_GENAI_USE_ENTERPRISE", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name in allowed and not os.environ.get(name, "").strip():
            os.environ[name] = value.strip().strip('"').strip("'")


def _assert_isolated_runtime() -> None:
    from src.engine.config import EngineConfig
    from src.llm_safety import check_external_llm_allowed

    config = EngineConfig.from_env()
    if config.enabled or config.collection.scheduler_enabled or config.external_calls_allowed:
        raise RuntimeError("Engine or scheduler safety flag is not off")
    if os.environ.get("LUMOS_ALLOW_ASSISTANT_LLM", "").lower() == "true":
        raise RuntimeError("Assistant LLM must remain disabled during experiment")
    check_external_llm_allowed("briefing_experiment")


def _load_results() -> Dict[str, Any]:
    if RESULTS_PATH.exists():
        result = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        # Discard the retired preflight counter.  It never represents a
        # generation request and must not influence the new budget.
        result.pop("model_list_calls", None)
        result.pop("models", None)
        result.pop("network_requests", None)
        result.setdefault("generation_requests", 0)
        result.setdefault("items", [])
        result["limits"] = LIMITS
        result.setdefault("grounding_tools", "disabled")
        return result
    return {"generation_requests": 0, "items": [], "limits": LIMITS,
            "grounding_tools": "disabled"}


def _save_results(result: Dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _usage_cost(model: str, metadata: Dict[str, Any]) -> float:
    prices = PRICING[model]
    return ((metadata.get("input_tokens") or 0) * prices["input"]
            + ((metadata.get("output_tokens") or 0) + (metadata.get("thinking_tokens") or 0)) * prices["output"]) / 1_000_000


def _check_generation_cap(result: Dict[str, Any]) -> None:
    if result["generation_requests"] >= LIMITS["max_requests"]:
        raise RuntimeError("generation request cap would be exceeded")


def _find_or_create_item(result: Dict[str, Any], source: Dict[str, Any], model: str) -> Dict[str, Any]:
    for item in result["items"]:
        if item["id"] == source["id"] and item["model"] == model:
            return item
    item = {"id": source["id"], "model": model, "source_url": source["url"],
            "published_at": source["published_at"], "source_title": source["title"]}
    result["items"].append(item)
    return item


def _run_content(result: Dict[str, Any], model: str, source: Dict[str, Any], platform_config) -> bool:
    """Issue exactly one content request; that request proves model access."""
    from src.signals.llm_briefing import AgentPlatformBriefingLLMClient, generate_content_briefing

    _check_generation_cap(result)
    client = AgentPlatformBriefingLLMClient(platform_config, model=model)
    response = generate_content_briefing(source, client=client)
    content = response.get("content_briefing") or {}
    metadata = response.get("metadata", {})
    result["generation_requests"] += 1
    item = _find_or_create_item(result, source, model)
    if response.get("status") != "success":
        # Never leave an older personalized card attached to a newly failed
        # content result for the same source/model.
        for key in ("source_facts_ko", "user_relevance_ko", "recommendation_reason_ko",
                    "why_it_matters_ko", "recommended_action_ko", "relevance_confidence",
                    "personalization_validation", "personalization_usage", "relevance_level", "relevance_basis"):
            item.pop(key, None)
    item.update({"content_status": response.get("status"),
                 "display_title_ko": content.get("display_title_ko", ""),
                 "display_summary_ko": content.get("display_summary_ko", ""),
                 "content_validation": content.get("_validation", metadata.get("validation_issues", {})),
                 "content_usage": _safe_metadata(metadata)})
    if response.get("status") != "success":
        item["personalize_status"] = "skipped_content_validation"
    item["estimated_cost_usd"] = round(_usage_cost(model, metadata), 8)
    _save_results(result)
    return item["content_status"] == "success"


def _run_personalization(result: Dict[str, Any], model: str, source: Dict[str, Any], platform_config) -> bool:
    """Issue exactly one personalization request only after successful content."""
    from src.signals.llm_briefing import AgentPlatformBriefingLLMClient, assess_relevance, generate_personalized_reason

    item = _find_or_create_item(result, source, model)
    if item.get("content_status") != "success":
        raise RuntimeError("personalization requires a successful content result")
    _check_generation_cap(result)
    client = AgentPlatformBriefingLLMClient(platform_config, model=model)
    relevance = assess_relevance(
        source, ["AI 에이전트 개발", "LangGraph 기반 워크플로", "에이전트 실행 중단 및 재개 안정성"],
    )
    grounding = item.get("content_validation", {}).get("checks", {}).get("fact_grounding", {}).get("details", [])
    content = {"display_title_ko": item.get("display_title_ko", ""),
               "display_summary_ko": item.get("display_summary_ko", ""),
               "grounded_facts": [
                   {"claim": fact.get("claim", ""), "source_quote": fact.get("source_quote", "")}
                   for fact in grounding if fact.get("claim") and fact.get("quote_found")
               ],
               "key_entities": [item.get("source_title", "")]}
    response = generate_personalized_reason(
        content, role="AI 에이전트 개발과 LangGraph 기반 워크플로를 운영하는 개발자",
        keywords=["AI 에이전트 개발", "LangGraph 기반 워크플로", "에이전트 실행 중단 및 재개 안정성"],
        client=client, relevance=relevance,
    )
    personalization = response.get("personalization") or {}
    metadata = response.get("metadata", {})
    result["generation_requests"] += 1
    item.update({"personalize_status": response.get("status"),
                 "source_facts_ko": personalization.get("source_facts_ko", ""),
                 "user_relevance_ko": personalization.get("user_relevance_ko", ""),
                 "recommendation_reason_ko": personalization.get("recommendation_reason_ko", ""),
                 "why_it_matters_ko": personalization.get("why_it_matters_ko", ""),
                 "recommended_action_ko": personalization.get("recommended_action_ko", ""),
                 "relevance_confidence": personalization.get("relevance_confidence", ""),
                 "relevance_level": relevance["level"], "relevance_basis": relevance["basis"],
                 "personalization_validation": personalization.get("_validation", {}),
                 "personalization_usage": _safe_metadata(metadata)})
    item["estimated_cost_usd"] = round(item.get("estimated_cost_usd", 0) + _usage_cost(model, metadata), 8)
    _save_results(result)
    return item["personalize_status"] == "success"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--phase", choices=("content", "personalize"))
    parser.add_argument("--source-index", type=int, default=0)
    parser.add_argument("--official-openai-engineering", action="store_true",
                        help="use the pinned public official-technology source; no network fetch")
    args = parser.parse_args()
    report = dry_run()
    if not args.execute:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if not args.phase:
        raise RuntimeError("--phase is required for live execution")
    _assert_isolated_runtime()
    _load_experiment_key()
    from src.signals.agent_platform import AgentPlatformConfig
    platform_config = AgentPlatformConfig.from_env()
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    if not 0 <= args.source_index < len(sources):
        raise RuntimeError("--source-index must identify one approved source")
    result = _load_results()
    source = OFFICIAL_OPENAI_ENGINEERING_SOURCE if args.official_openai_engineering else sources[args.source_index]
    if args.phase == "content":
        _run_content(result, BASELINE_MODEL, source, platform_config)
    else:
        _run_personalization(result, BASELINE_MODEL, source, platform_config)
    _save_results(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

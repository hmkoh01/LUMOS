"""Explicitly approved one-shot quality check for services 15163956 and 15125273.

Not a runtime worker: at most one request per source, no retry, no DB writes.
Only sanitised aggregate diagnostics are persisted; previews stay in memory.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sources.collectors.base import SourceQuery
from src.sources.collectors.mss_support_program import MSSSupportProgramCollector
from src.sources.collectors.public_institution_jobs import PublicInstitutionJobsCollector
from src.sources.diagnostics import ascii_console_summary, build_safe_report, write_utf8_report
from src.sources.domestic_collection_strategy import classify_support_program_profiles, has_developer_role_evidence

REPORT_DIR = ROOT / "artifacts" / "api-key-audit"
MAX_ROWS = 20


class Tracker:
    http_status: int | None = None
    body_result_code: str | None = None


def fetcher(tracker: Tracker) -> Callable[[str, float, dict[str, str]], Any]:
    def fetch(url: str, timeout: float, headers: dict[str, str]) -> Any:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
                tracker.http_status = int(response.getcode())
                payload = json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            tracker.http_status = int(exc.code)
            # Do not read, print, or persist a provider error body.
            raise RuntimeError(f"HTTP {exc.code}") from None
        if isinstance(payload, dict):
            value = payload.get("resultCode")
            tracker.body_result_code = str(value) if value is not None else None
        return payload
    return fetch


def _preview(item: dict[str, Any], interest: str, kind: str) -> dict[str, str]:
    """Factual process-memory preview. It is never put in diagnostic JSON."""
    data = item.get("metrics_json") or {}
    if kind == "job":
        return {
            "title": str(item.get("title") or ""),
            "summary": f"공고 기간: {data.get('announcement_start_at') or '미확인'}~{data.get('announcement_end_at') or '미확인'}",
            "reason": f"'{interest}'와 직무 정보가 직접 일치합니다.",
        }
    return {
        "title": str(item.get("title") or ""),
        "summary": f"모집 기간: {data.get('application_start_at') or '미확인'}~{data.get('application_end_at') or '미확인'}",
        "reason": f"'{interest}' 근거가 제목·목적·대상·지원유형에 있습니다.",
    }


def _job_quality(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"with_date": 0, "with_url": 0, "developer_direct": 0, "junior_developer": 0}
    excluded: dict[str, int] = {}
    previews: list[dict[str, str]] = []
    junior_terms = ("신입", "new hire", "entry")
    for item in items:
        data = item.get("metrics_json") or {}
        if data.get("announcement_start_at") or data.get("announcement_end_at"):
            counts["with_date"] += 1
        if item.get("url"):
            counts["with_url"] += 1
        role_text = " ".join((str(item.get("title") or ""), str(data.get("job_type") or ""), str(data.get("job_classification") or ""), str(data.get("recruitment_type") or ""))).casefold()
        if not has_developer_role_evidence(item.get("title"), data.get("job_type"), data.get("job_classification"), data.get("recruitment_type")):
            excluded["developer_role_not_directly_confirmed"] = excluded.get("developer_role_not_directly_confirmed", 0) + 1
            continue
        counts["developer_direct"] += 1
        if not item.get("url"):
            excluded["official_source_url_missing"] = excluded.get("official_source_url_missing", 0) + 1
            continue
        if not any(term in role_text for term in junior_terms):
            excluded["junior_status_not_directly_confirmed"] = excluded.get("junior_status_not_directly_confirmed", 0) + 1
            continue
        counts["junior_developer"] += 1
        if len(previews) < 3:
            previews.append(_preview(item, "신입 개발자 채용", "job"))
    return {"counts": counts, "excluded": excluded, "previews": previews}


def _support_quality(items: list[dict[str, Any]]) -> dict[str, Any]:
    profiles = {name: 0 for name in ("technical_startup", "general_startup", "small_business", "digital_commerce", "online_market_access")}
    counts = {"with_complete_window": 0, "with_url": 0}
    excluded: dict[str, int] = {}
    previews: dict[str, list[dict[str, str]]] = {name: [] for name in profiles}
    for item in items:
        data = item.get("metrics_json") or {}
        if data.get("application_start_at") and data.get("application_end_at"):
            counts["with_complete_window"] += 1
        if item.get("url"):
            counts["with_url"] += 1
        matched = classify_support_program_profiles(item)
        if not matched:
            excluded["no_direct_profile_evidence"] = excluded.get("no_direct_profile_evidence", 0) + 1
            continue
        if not item.get("url"):
            excluded["official_source_url_missing"] = excluded.get("official_source_url_missing", 0) + 1
            continue
        for profile in matched:
            profiles[profile] += 1
            if len(previews[profile]) < 3:
                previews[profile].append(_preview(item, profile, "support"))
    return {"counts": counts, "profiles": profiles, "excluded": excluded, "previews": previews}


def collect(source: str, collector: Any, query: SourceQuery, tracker: Tracker) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = collector.collect([query], MAX_ROWS)
    classification = next((str(value).split("=", 1)[1] for value in result.warnings if "response_classification=" in str(value)), None)
    report = build_safe_report(source, result, request_limit=1, http_status=tracker.http_status, provider_code=tracker.body_result_code, request_count=1, response_classification=classification)
    write_utf8_report(REPORT_DIR / f"{source}-strategy-check.json", report)
    print(ascii_console_summary(report))
    return result.item_dicts(), report


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    if not (os.environ.get("PUBLIC_DATA_PORTAL_SERVICE_KEY", "").strip() or os.environ.get("MSS_SUPPORT_PROGRAM_API_KEY", "").strip()):
        print(json.dumps({"status": "not_run", "reason": "public_data_portal_key_missing"}, ensure_ascii=True))
        return
    support_tracker, jobs_tracker = Tracker(), Tracker()
    # Exactly one request per source. No retry, pagination, or service startup.
    support_items, _ = collect("mss_support_program", MSSSupportProgramCollector(fetch_json=fetcher(support_tracker)), SourceQuery(source="mss_support_program", query="", params={"sprtBizYr": "2026", "pageNo": 1, "collection_scope": "mss_support_program:2026"}), support_tracker)
    jobs_items, _ = collect("public_institution_jobs", PublicInstitutionJobsCollector(fetch_json=fetcher(jobs_tracker)), SourceQuery(source="public_institution_jobs", query="junior_developer", params={"pageNo": 1, "ongoingYn": "Y", "recrutPbancTtl": "개발", "resultType": "json", "collection_scope": "public_institution_jobs:current-opportunities", "direct_evidence_terms": ["개발", "developer", "소프트웨어", "software", "programming", "coding"]}), jobs_tracker)
    # Console only; source titles never enter the persisted diagnostic report.
    print(json.dumps({"evaluation": {"mss_support_program": _support_quality(support_items), "public_institution_jobs": _job_quality(jobs_items)}}, ensure_ascii=True, separators=(",", ":")))


if __name__ == "__main__":
    main()

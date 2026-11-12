"""One-shot, operator-approved quality check for three domestic metadata APIs.

It must be run only with an explicit request budget. It does not write a DB,
does not start application services, and persists only sanitized diagnostics.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "artifacts" / "api-key-audit"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.engine.llm.domestic_preview import build_domestic_preview, evaluate_personalised_item
from src.sources.collectors.base import SourceQuery
from src.sources.collectors.kopis import KOPISCollector
from src.sources.collectors.opendart import OpenDARTCollector
from src.sources.collectors.tourapi import TourAPIFestivalCollector
from src.sources.diagnostics import ascii_console_summary, build_safe_report, write_utf8_report

class _Tracker:
    def __init__(self) -> None:
        self.http_status: int | None = None
        self.provider_code: str | None = None


def _json_fetcher(tracker: _Tracker) -> Callable[[str, float, dict[str, str]], Any]:
    def fetch(url: str, timeout: float, headers: dict[str, str]) -> Any:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
                tracker.http_status = int(response.getcode())
                payload = json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            tracker.http_status = int(exc.code)
            body = exc.read(32_000).decode("utf-8", errors="replace")
            # Parse only bounded provider status fields; never keep the body.
            tracker.provider_code, _ = TourAPIFestivalCollector._provider_error_fields(body)
            raise RuntimeError(f"HTTP {exc.code}" + (f"; provider_code={tracker.provider_code}" if tracker.provider_code else "")) from None
        if isinstance(payload, dict):
            header = ((payload.get("response") or {}).get("header") or {})
            tracker.provider_code = str(header.get("resultCode") or payload.get("status") or "") or None
        return payload
    return fetch


def _xml_fetcher(tracker: _Tracker) -> Callable[[str, float, dict[str, str]], str]:
    def fetch(url: str, timeout: float, headers: dict[str, str]) -> str:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
                tracker.http_status = int(response.getcode())
                text = response.read(1_000_000).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            tracker.http_status = int(exc.code)
            body = exc.read(32_000).decode("utf-8", errors="replace")
            tracker.provider_code, _ = TourAPIFestivalCollector._provider_error_fields(body)
            raise RuntimeError(f"HTTP {exc.code}" + (f"; provider_code={tracker.provider_code}" if tracker.provider_code else "")) from None
        try:
            tracker.provider_code = (ET.fromstring(text).findtext(".//resultCode") or "").strip() or None
        except ET.ParseError:
            pass
        return text
    return fetch


def _basic(item: dict[str, Any]) -> tuple[bool, str]:
    metrics = item.get("metrics_json") or {}
    kind = metrics.get("content_kind")
    if not item.get("url"):
        return False, "official_source_url_missing"
    if kind in {"culture_event", "performance"}:
        if metrics.get("event_status") not in {"upcoming", "ongoing"}:
            return False, "event_not_active"
        if not metrics.get("event_start_at"):
            return False, "event_date_missing"
        if not metrics.get("venue"):
            return False, "venue_missing"
    elif kind == "corporate_disclosure" and not metrics.get("receipt_at"):
        return False, "receipt_date_missing"
    return True, "basic_requirements_met"


def _evaluate(items: list[dict[str, Any]], cases: list[tuple[str, str, str]]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for label, interest, region in cases:
        passed: list[dict[str, str]] = []
        reasons: dict[str, int] = {}
        basic_count = 0
        seen: set[str] = set()
        for item in items:
            item_id = str(item.get("source_item_id") or "")
            if item_id in seen:
                reasons["duplicate"] = reasons.get("duplicate", 0) + 1
                continue
            seen.add(item_id)
            valid, reason = _basic(item)
            if not valid:
                reasons[reason] = reasons.get(reason, 0) + 1
                continue
            basic_count += 1
            outcome = evaluate_personalised_item(item, interest, preferred_region=region)
            if outcome["eligible"] != "true":
                reasons[outcome["reason"]] = reasons.get(outcome["reason"], 0) + 1
                continue
            preview = build_domestic_preview(item, interest)
            if preview.get("status") != "ready":
                reasons[preview.get("reason", "preview_withheld")] = reasons.get(preview.get("reason", "preview_withheld"), 0) + 1
                continue
            # This return value stays in memory and process stdout only. It is
            # intentionally excluded from diagnostics because it includes title and URL.
            passed.append({key: str(preview[key]) for key in ("display_title_ko", "summary_ko", "recommendation_reason_ko", "source_url")})
        results[label] = {"received": len(items), "basic": basic_count, "personalised": len(passed), "excluded": reasons, "previews": passed[:3]}
    return results


def _collect(source: str, collector: Any, query: SourceQuery, tracker: _Tracker) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = collector.collect([query], 10)
    report = build_safe_report(source, result, request_limit=1, http_status=tracker.http_status, provider_code=tracker.provider_code, request_count=1)
    write_utf8_report(REPORT_DIR / f"{source}-personalization-check.json", report)
    print(ascii_console_summary(report))
    return result.item_dicts(), report


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    required = ("TOURAPI_SERVICE_KEY", "OPENDART_API_KEY", "KOPIS_API_KEY")
    if any(not os.environ.get(name, "").strip() for name in required):
        # No request occurs if any approved source is not configured.
        print(json.dumps({"status": "not_run", "reason": "required_key_missing"}, ensure_ascii=True))
        return

    today = date.today()
    tour_tracker, dart_tracker, kopis_tracker = _Tracker(), _Tracker(), _Tracker()
    tour_items, _ = _collect("tourapi", TourAPIFestivalCollector(fetch_json=_json_fetcher(tour_tracker)), SourceQuery(source="tourapi", query="", params={"event_start_date": today.strftime("%Y%m%d")}), tour_tracker)
    dart_items, _ = _collect("opendart", OpenDARTCollector(fetch_json=_json_fetcher(dart_tracker)), SourceQuery(source="opendart", query="", params={"bgn_de": (today - timedelta(days=30)).strftime("%Y%m%d"), "end_de": today.strftime("%Y%m%d"), "page_count": 10}), dart_tracker)
    kopis_items, _ = _collect("kopis", KOPISCollector(fetch_text=_xml_fetcher(kopis_tracker)), SourceQuery(source="kopis", query="", params={"stdate": today.strftime("%Y%m%d"), "eddate": (today + timedelta(days=180)).strftime("%Y%m%d")}), kopis_tracker)

    # The company control is derived from the received, non-persisted data;
    # this does not claim an actual user's preference.
    company = next((str(item.get("author") or "").strip() for item in dart_items if str(item.get("author") or "").strip()), "__no_company__")
    evaluation = {
        "tourapi": _evaluate(tour_items, [("seoul_culture", "서울 문화행사", "서울"), ("busan_festival", "부산 지역 축제", "부산"), ("jazz_or_musical", "재즈·뮤지컬 공연", "")]),
        "kopis": _evaluate(kopis_items, [("seoul_culture", "서울 문화행사", "서울"), ("busan_festival", "부산 지역 축제", "부산"), ("jazz_or_musical", "재즈·뮤지컬 공연", "")]),
        "opendart": _evaluate(dart_items, [("received_company_control", company, ""), ("semiconductor_industry", "반도체", ""), ("general_economy", "경제", "")]),
    }
    # stdout only: ensure_ascii is safe in Windows terminals. Do not write this
    # value to disk because it contains source title/link derived previews.
    print(json.dumps({"evaluation": evaluation}, ensure_ascii=True, separators=(",", ":")))


if __name__ == "__main__":
    main()

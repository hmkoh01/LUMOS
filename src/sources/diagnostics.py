"""Safe persistence and console output for isolated source diagnostics.

This module deliberately receives collector results *after* a bounded request,
but never stores raw payloads, request URLs, authentication data, titles, or
other source text.  A UTF-8 report is written before its ASCII-only console
summary is printed so a Windows CP949 console cannot erase diagnostic evidence.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping
from urllib.parse import urlparse


_HTTP_STATUS = re.compile(r"\bHTTP\s+(\d{3})\b", re.IGNORECASE)
_PROVIDER_CODE = re.compile(r"\b(?:provider_)?code\s*=\s*([A-Za-z0-9_-]{1,80})", re.IGNORECASE)
_API_CODE = re.compile(r"\bAPI error\s+([A-Za-z0-9_-]{1,80})", re.IGNORECASE)


def build_safe_report(
    source: str,
    result: Any,
    *,
    request_limit: int,
    attempted: bool = True,
    http_status: int | None = None,
    provider_code: str | None = None,
    request_count: int = 1,
    response_classification: str | None = None,
    upstream_received_item_count: int | None = None,
    source_counts: Mapping[str, int] | None = None,
) -> Dict[str, Any]:
    """Reduce a CollectorResult to non-sensitive, schema-controlled facts."""
    items = list(getattr(result, "items", []) or [])
    errors = list(getattr(result, "errors", []) or [])
    warnings = list(getattr(result, "warnings", []) or [])
    # ``request_limit`` counts outbound calls, not returned records. Each
    # record summary is whitelisted and has no source text, so retaining the
    # bounded collector result keeps normalisation and quality counts honest.
    records = [_safe_item_summary(item) for item in items]
    return {
        "schema_version": 1,
        "source": _safe_identifier(source),
        "attempted": bool(attempted),
        "request_limit": max(0, int(request_limit)),
        "outcome": _outcome(errors, attempted),
        "provider": _provider_summary(errors, http_status=http_status, provider_code=provider_code),
        "request_count": max(0, int(request_count)),
        "response_classification": _safe_identifier(response_classification),
        "source_counts": _safe_counts(source_counts),
        "received_item_count": len(items),
        # A count only: this distinguishes a provider's page size from items
        # discarded by the collector without retaining any raw source data.
        "upstream_received_item_count": (
            max(0, int(upstream_received_item_count))
            if upstream_received_item_count is not None else None
        ),
        "normalised_item_count": len(records),
        "quality": _quality_summary(records),
        "warnings": _safe_warning_codes(warnings),
        # Record-level summaries intentionally omit title, author, URL,
        # abstract, raw JSON and all source text. They preserve only the
        # fields needed to decide if a future quality inspection is warranted.
        "records": records,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def write_utf8_report(path: Path, report: Mapping[str, Any]) -> Path:
    """Persist an already-sanitised report as UTF-8 JSON, never a raw result."""
    safe_report = _validate_safe_report(dict(report))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(safe_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def ascii_console_summary(report: Mapping[str, Any]) -> str:
    """Return a CP949-safe, single-line summary suitable for Windows stdout."""
    safe_report = _validate_safe_report(dict(report))
    summary = {
        "attempted": safe_report["attempted"],
        "normalised_item_count": safe_report["normalised_item_count"],
        "outcome": safe_report["outcome"],
        "provider": safe_report["provider"],
        "received_item_count": safe_report["received_item_count"],
        "upstream_received_item_count": safe_report.get("upstream_received_item_count"),
        "source": safe_report["source"],
        "source_counts": safe_report.get("source_counts", {}),
    }
    return json.dumps(summary, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _safe_item_summary(item: Any) -> Dict[str, Any]:
    metrics = getattr(item, "metrics_json", {}) or {}
    raw = getattr(item, "raw_json", {}) or {}
    return {
        "has_published_at": bool(getattr(item, "published_at", None)),
        "has_source_url": bool(getattr(item, "url", None)),
        # Presence-only recruitment metadata. These flags deliberately retain
        # neither employer, role, region, nor any source URL text.
        "has_institution": bool(getattr(item, "author", None)),
        "has_job_metadata": bool(metrics.get("job_type") or metrics.get("job_classification")),
        "has_region": bool(metrics.get("region")),
        "has_announcement_date": bool(metrics.get("announcement_start_at")),
        "has_official_http_url": _is_http_url(getattr(item, "url", "")),
        "has_doi": bool(metrics.get("doi") or raw.get("doi")),
        "content_kind": _safe_identifier(metrics.get("content_kind")),
        "date_precision": _safe_identifier(metrics.get("publication_date_precision")),
        "opportunity_status": _safe_identifier(
            metrics.get("event_status") or metrics.get("application_window_status")
        ),
        "research_role": _safe_identifier(metrics.get("research_role")),
        "has_event_end_at": bool(metrics.get("event_end_at")),
        "has_venue": bool(metrics.get("venue")),
        "has_application_start_at": bool(metrics.get("application_start_at")),
        "has_application_end_at": bool(metrics.get("application_end_at")),
        "has_support_target": bool(metrics.get("support_target")),
        "recommendation_eligible": _recommendation_eligible(item),
    }


def _quality_summary(records: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    values = list(records)
    return {
        "with_published_at": sum(bool(record.get("has_published_at")) for record in values),
        "with_source_url": sum(bool(record.get("has_source_url")) for record in values),
        "with_institution": sum(bool(record.get("has_institution")) for record in values),
        "with_job_metadata": sum(bool(record.get("has_job_metadata")) for record in values),
        "with_region": sum(bool(record.get("has_region")) for record in values),
        "with_announcement_date": sum(bool(record.get("has_announcement_date")) for record in values),
        "with_official_http_url": sum(bool(record.get("has_official_http_url")) for record in values),
        "with_doi": sum(bool(record.get("has_doi")) for record in values),
        # ``unknown`` is intentionally retained as a conservative state, not
        # counted as a verified open/closed opportunity condition.
        "known_opportunity_status": sum(
            str(record.get("opportunity_status") or "").casefold() not in {"", "unknown"}
            for record in values
        ),
        "with_event_end_at": sum(bool(record.get("has_event_end_at")) for record in values),
        "with_venue": sum(bool(record.get("has_venue")) for record in values),
        "with_application_start_at": sum(bool(record.get("has_application_start_at")) for record in values),
        "with_application_end_at": sum(bool(record.get("has_application_end_at")) for record in values),
        "with_support_target": sum(bool(record.get("has_support_target")) for record in values),
        "recommendation_eligible": sum(bool(record.get("recommendation_eligible")) for record in values),
    }


def _outcome(errors: List[Any], attempted: bool) -> str:
    if not attempted:
        return "not_attempted"
    if not errors:
        return "success"
    text = " ".join(str(error) for error in errors)
    if _HTTP_STATUS.search(text) or "API error" in text:
        return "provider_error"
    if "network request failed" in text:
        return "network_error"
    if "invalid" in text.lower() or "parse" in text.lower():
        return "invalid_response"
    if "required" in text.lower() or "configuration" in text.lower():
        return "configuration_error"
    return "collector_error"


def _provider_summary(errors: List[Any], *, http_status: int | None = None, provider_code: str | None = None) -> Dict[str, Any]:
    text = " ".join(str(error) for error in errors)
    status = _HTTP_STATUS.search(text)
    parsed_match = _PROVIDER_CODE.search(text) or _API_CODE.search(text)
    parsed_code = parsed_match.group(1) if parsed_match else None
    return {
        "http_status": int(http_status) if http_status is not None else (int(status.group(1)) if status else None),
        "provider_code": _safe_identifier(provider_code) or parsed_code,
    }


def _safe_warning_codes(warnings: Iterable[Any]) -> List[str]:
    # Warnings are not free-form publisher text. Keep only project's bounded
    # operational counters, so an upstream response cannot inject content.
    allowed_prefixes = ("msit_", "openalex_", "mss_support_", "public_jobs_", "opendart_")
    return [str(warning)[:160] for warning in warnings if str(warning).startswith(allowed_prefixes)]


def _recommendation_eligible(item: Any) -> bool:
    """Classify an opportunity without persisting its untrusted title text."""
    try:
        from src.sources.content_rights import classify_opportunity_status

        return classify_opportunity_status(str(getattr(item, "title", ""))) != "not_new_opportunity"
    except Exception:
        # Failure to classify is conservative: never claim recommendation fit.
        return False


def _safe_identifier(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", text):
        return None
    return text


def _is_http_url(value: Any) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _safe_counts(values: Mapping[str, int] | None) -> Dict[str, int]:
    """Keep only predefined numeric counters, never upstream text or IDs."""
    allowed = {
        "directory_record_count", "exact_name_match_count", "ambiguous_name_match_count",
        "corp_code_matched_item_count", "corp_code_mismatched_item_count",
        "direct_interest_evidence_count", "metadata_card_preview_ready_count",
    }
    return {
        key: max(0, int(value))
        for key, value in dict(values or {}).items()
        if key in allowed
    }


def _validate_safe_report(report: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "schema_version", "source", "attempted", "request_limit", "request_count", "response_classification", "source_counts", "outcome", "provider",
        "received_item_count", "upstream_received_item_count", "normalised_item_count", "quality", "warnings", "records", "generated_at_utc",
    }
    return {key: report[key] for key in allowed if key in report}

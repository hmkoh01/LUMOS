import json

from src.sources.collectors.base import CollectedItem, CollectorResult
from src.sources.diagnostics import ascii_console_summary, build_safe_report, write_utf8_report


def test_safe_diagnostic_uses_utf8_file_and_ascii_only_console_summary(tmp_path):
    result = CollectorResult(
        source="tourapi",
        items=[CollectedItem(
            source="tourapi", source_item_id="festival-1", url="https://example.test/secret?serviceKey=never-store",
            title="한글 제목 — 공연 & 전시 🎭", author="개인정보가 될 수 있는 작성자",
            published_at="2026-11-09T00:00:00", summary="원문 응답은 저장하지 않는다.",
            metrics_json={"content_kind": "culture_event", "event_status": "upcoming"},
            raw_json={"authorization": "secret", "body": "untrusted raw response"},
        )],
        errors=[],
        warnings=["openalex_rate_limit_remaining=9", "publisher text must not persist: 한글"],
    )
    report = build_safe_report("tourapi", result, request_limit=10)
    target = write_utf8_report(tmp_path / "diagnostic.json", report)
    stored = target.read_text(encoding="utf-8")
    loaded = json.loads(stored)

    assert loaded["outcome"] == "success"
    assert loaded["records"][0]["content_kind"] == "culture_event"
    assert loaded["records"][0]["recommendation_eligible"] is True
    assert "한글 제목" not in stored
    assert "serviceKey" not in stored
    assert "authorization" not in stored.lower()
    assert "원문 응답" not in stored

    console = ascii_console_summary(report)
    assert console.encode("cp949")
    assert all(ord(char) < 128 for char in console)


def test_safe_diagnostic_keeps_only_provider_status_and_code_from_errors():
    result = CollectorResult(
        source="tourapi",
        errors=["network request failed: HTTP 403: Forbidden; provider_code=SERVICE_ACCESS_DENIED; provider_message=do not store this"],
    )
    report = build_safe_report("tourapi", result, request_limit=10)

    assert report["outcome"] == "provider_error"
    assert report["provider"] == {"http_status": 403, "provider_code": "SERVICE_ACCESS_DENIED"}
    assert "provider_message" not in json.dumps(report)


def test_request_limit_counts_requests_not_safe_normalised_records():
    result = CollectorResult(source="tourapi", items=[
        CollectedItem(source="tourapi", source_item_id="one", title="one", url="https://example.test/one"),
        CollectedItem(source="tourapi", source_item_id="two", title="two", url="https://example.test/two"),
    ])
    report = build_safe_report("tourapi", result, request_limit=1)
    assert report["request_limit"] == 1
    assert report["normalised_item_count"] == 2
    assert report["quality"]["with_source_url"] == 2


def test_safe_diagnostic_keeps_job_field_presence_without_source_text():
    result = CollectorResult(source="public_institution_jobs", items=[
        CollectedItem(
            source="public_institution_jobs", source_item_id="job-1",
            title="must not persist", author="must not persist", url="https://official.example/job-1",
            published_at="2026-11-11", metrics_json={
                "content_kind": "public_institution_job", "announcement_start_at": "2026-11-11",
                "job_type": "must not persist", "job_classification": "must not persist", "region": "must not persist",
            },
        ),
    ])
    report = build_safe_report("public_institution_jobs", result, request_limit=1)
    record = report["records"][0]
    assert all(record[name] is True for name in (
        "has_institution", "has_job_metadata", "has_region", "has_announcement_date", "has_official_http_url",
    ))
    assert report["quality"]["with_job_metadata"] == 1
    assert "must not persist" not in json.dumps(report)


def test_unknown_opportunity_status_is_not_reported_as_a_verified_status():
    result = CollectorResult(source="public_institution_jobs", items=[
        CollectedItem(
            source="public_institution_jobs", source_item_id="job-unknown",
            title="unknown", url="",
            metrics_json={"application_window_status": "unknown"},
        ),
    ])
    report = build_safe_report("public_institution_jobs", result, request_limit=1)
    assert report["quality"]["known_opportunity_status"] == 0


def test_safe_diagnostic_accepts_explicit_success_transport_without_urls_or_keys():
    report = build_safe_report("tourapi", CollectorResult(source="tourapi"), request_limit=1,
                               request_count=1, http_status=200, provider_code="0000",
                               response_classification="schema_valid_unverified_code", upstream_received_item_count=10,
                               source_counts={"exact_name_match_count": 1, "untrusted_title": 99})
    assert report["request_count"] == 1
    assert report["provider"] == {"http_status": 200, "provider_code": "0000"}
    assert report["response_classification"] == "schema_valid_unverified_code"
    assert report["upstream_received_item_count"] == 10
    assert report["source_counts"] == {"exact_name_match_count": 1}

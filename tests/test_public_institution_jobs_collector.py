import os
from unittest.mock import patch

from src.engine.llm.domestic_preview import build_domestic_preview, evaluate_personalised_item
from src.sources.collectors.base import SourceQuery
from src.sources.collectors.public_institution_jobs import PublicInstitutionJobsCollector
from src.sources.source_registry import SOURCE_CAPABILITIES, source_availability, source_usage_permission


PAYLOAD = {"resultCode": 0, "resultMsg": "normal", "totalCount": 3, "result": [
    {"item": {"recrutPblntSn": "J-1", "recrutPbancTtl": "Junior software developer internship", "instNm": "Public Agency", "pbancBgngYmd": "20990101", "pbancEndYmd": "20990131", "hireTypeNmLst": "intern", "workRgnNmLst": "Seoul", "ncsCdNmLst": "software development", "ongoingYn": "Y", "srcUrl": "https://official.example/J-1", "recrutSeNm": "new hire", "recrutNope": 3}},
    {"item": {"recrutPblntSn": "J-1", "recrutPbancTtl": "duplicate", "ongoingYn": "Y"}},
    {"item": {"recrutPblntSn": "J-2", "recrutPbancTtl": "Other role", "instNm": "Other", "ongoingYn": "Y", "srcUrl": ""}},
]}


def _query(interest=""):
    return SourceQuery(source="public_institution_jobs", query=interest, params={"raw_interest": interest, "ongoingYn": "Y", "resultType": "json"})


def test_parses_result_array_item_and_deduplicates_without_claiming_application_open():
    collector = PublicInstitutionJobsCollector(fetch_json=lambda *_args: PAYLOAD)
    with patch.dict(os.environ, {"PUBLIC_DATA_PORTAL_SERVICE_KEY": "test-key"}, clear=False):
        result = collector.collect([_query()], 10)
    assert [item.source_item_id for item in result.items] == ["J-1", "J-2"]
    item = result.item_dicts()[0]
    assert item["metrics_json"]["application_window_status"] == "unknown"
    assert item["metrics_json"]["provider_ongoing"] == "Y"
    assert item["metrics_json"]["provider_pbanc_end_ymd_unverified"] == "2099-01-31"
    assert "announcement_end_at" not in item["metrics_json"]
    assert "application_deadline_at" not in item["metrics_json"]
    assert "public_jobs_rejected_duplicate=1" in result.warnings


def test_error_empty_and_missing_key_do_not_normalise_or_retry():
    collector = PublicInstitutionJobsCollector(fetch_json=lambda *_args: {"resultCode": 7, "resultMsg": "provider error", "result": PAYLOAD["result"]})
    with patch.dict(os.environ, {"PUBLIC_DATA_PORTAL_SERVICE_KEY": "test-key"}, clear=False):
        assert "provider_error_message" in collector.collect([_query()], 10).errors[0]
    calls = []
    missing = PublicInstitutionJobsCollector(fetch_json=lambda *_args: calls.append(1) or PAYLOAD)
    with patch.dict(os.environ, {"PUBLIC_DATA_PORTAL_SERVICE_KEY": "", "PUBLIC_INSTITUTION_JOBS_API_KEY": ""}, clear=False):
        assert "PUBLIC_DATA_PORTAL_SERVICE_KEY" in missing.collect([_query()], 10).errors[0]
    assert not calls


def test_unverified_body_code_with_valid_documented_shape_is_isolation_only():
    payload = {**PAYLOAD, "resultCode": 200, "resultMsg": "response received"}
    collector = PublicInstitutionJobsCollector(fetch_json=lambda *_args: payload)
    with patch.dict(os.environ, {"PUBLIC_DATA_PORTAL_SERVICE_KEY": "test-key"}, clear=False):
        result = collector.collect([_query()], 10)
    assert len(result.items) == 2
    assert "public_jobs_response_classification=schema_valid_unverified_code" in result.warnings


def test_documented_zero_code_is_confirmed_only_with_valid_shape():
    collector = PublicInstitutionJobsCollector(fetch_json=lambda *_args: PAYLOAD)
    with patch.dict(os.environ, {"PUBLIC_DATA_PORTAL_SERVICE_KEY": "test-key"}, clear=False):
        result = collector.collect([_query()], 10)
    assert "public_jobs_response_classification=confirmed_success" in result.warnings


def test_missing_result_code_is_rejected_even_when_item_shape_is_valid():
    payload = {"result": PAYLOAD["result"], "resultMsg": "response received"}
    collector = PublicInstitutionJobsCollector(fetch_json=lambda *_args: payload)
    with patch.dict(os.environ, {"PUBLIC_DATA_PORTAL_SERVICE_KEY": "test-key"}, clear=False):
        result = collector.collect([_query()], 10)
    assert "result_code_missing" in result.errors[0]


def test_job_interest_preview_requires_direct_job_metadata_and_official_url():
    collector = PublicInstitutionJobsCollector(fetch_json=lambda *_args: PAYLOAD)
    with patch.dict(os.environ, {"PUBLIC_DATA_PORTAL_SERVICE_KEY": "test-key"}, clear=False):
        item = collector.collect([_query()], 10).item_dicts()[0]
    assert evaluate_personalised_item(item, "software developer internship")["eligible"] == "true"
    assert evaluate_personalised_item(item, "accounting")["reason"] == "career_interest_mismatch"
    preview = build_domestic_preview(item, "software developer internship")
    assert preview["status"] == "ready"
    assert preview["source_url"] == "https://official.example/J-1"
    assert preview["source_name_ko"] == "\uc7ac\uc815\uacbd\uc81c\ubd80 \uacf5\uacf5\uae30\uad00 \ucc44\uc6a9\uc815\ubcf4 \uc870\ud68c\uc11c\ube44\uc2a4"
    assert preview["application_deadline_status"] == "unknown"
    assert "software development" in preview["summary_ko"]
    assert "Seoul" in preview["summary_ko"]
    assert "2099-01-31" not in preview["summary_ko"]
    assert "deadline" not in preview["summary_ko"].casefold()


def test_intern_canary_spec_is_one_list_request_and_uses_no_unverified_code_or_deadline_filter():
    from datetime import date
    from src.sources.operational_canary import canary_spec

    spec = canary_spec("public_institution_jobs", today=date(2026, 11, 11))
    assert (spec.max_requests, spec.max_items, spec.max_retries, spec.llm_allowed) == (1, 10, 0, False)
    assert spec.query.params["recrutPbancTtl"] == "\uc778\ud134"
    assert spec.query.params["direct_evidence_terms"] == ("\uc778\ud134", "intern")
    assert "recrutSe" not in spec.query.params
    assert "hireTypeLst" not in spec.query.params
    assert "ncsCdLst" not in spec.query.params
    assert "pbancEndYmd" not in spec.query.params


def test_source_schema_is_official_but_global_permission_gate_is_unchanged():
    assert SOURCE_CAPABILITIES["public_institution_jobs"]["schema_status"] == "official"
    assert source_availability("public_institution_jobs", {})["state"] == "permission_review"
    assert source_usage_permission("public_institution_jobs", "metadata_display")["state"] == "permission_review"
    assert source_usage_permission("public_institution_jobs", "llm_processing")["state"] == "not_granted"
    assert source_usage_permission("public_institution_jobs", "image_or_attachment_use")["state"] == "not_in_scope"
    assert source_usage_permission("public_institution_jobs", "production_api_access")["state"] == "service_approval_and_operator_record_required"

import os
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from src.sources.collectors.base import SourceQuery
from src.sources.collectors.msit_announcements import MSITAnnouncementCollector
from src.sources.source_registry import source_availability


PAYLOAD = {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"}, "body": {"items": {"item": [
    {"subject": "2026 AI semiconductor R&D call", "viewUrl": "https://msit.example/a", "deptName": "R&D Policy", "pressDt": "2026-11-08", "fileName": "notice.pdf", "fileUrl": "https://msit.example/a.pdf"},
    {"subject": "Unrelated marine event", "viewUrl": "https://msit.example/b", "deptName": "Other", "pressDt": "invalid"},
]}}}}


def _query(term="semiconductor"):
    return [SourceQuery(source="msit_announcements", query=term, params={"raw_interest": term})]


def test_normalises_official_documented_fields_and_filters_interest():
    collector = MSITAnnouncementCollector(fetch_json=lambda *_args: PAYLOAD)
    with patch.dict(os.environ, {"MSIT_ANNOUNCEMENT_API_KEY": "test-key"}, clear=False):
        result = collector.collect(_query(), limit=5)
    assert not result.errors
    assert len(result.items) == 1
    item = result.item_dicts()[0]
    assert item["title"] == "2026 AI semiconductor R&D call"
    assert item["url"] == "https://msit.example/a"
    assert item["author"] == "R&D Policy"
    assert item["published_at"].startswith("2026-11-08")
    assert item["metrics_json"]["application_window_status"] == "unknown"
    assert item["raw_json"]["service_id"] == "15074634"
    assert item["raw_json"]["file_url"] == "https://msit.example/a.pdf"


def test_missing_key_does_not_open_network_and_errors_are_terminal():
    calls = []
    collector = MSITAnnouncementCollector(fetch_json=lambda *_args: calls.append(1) or PAYLOAD)
    with patch.dict(os.environ, {"MSIT_ANNOUNCEMENT_API_KEY": ""}, clear=False):
        result = collector.collect(_query(), limit=5)
    assert result.errors == ["MSIT_ANNOUNCEMENT_API_KEY is required; no request was made."]
    assert not calls

    denied = {"response": {"header": {"resultCode": "20", "resultMsg": "PERMISSION_DENIED"}}}
    with patch.dict(os.environ, {"MSIT_ANNOUNCEMENT_API_KEY": "test-key"}, clear=False):
        assert "API error 20" in MSITAnnouncementCollector(fetch_json=lambda *_args: denied).collect(_query(), 5).errors[0]


def test_source_is_available_for_documented_metadata_when_key_is_configured():
    with patch.dict(os.environ, {"MSIT_ANNOUNCEMENT_API_KEY": "test-key"}, clear=False):
        state = source_availability("msit_announcements", {})
    assert state["state"] == "available"
    assert state["capabilities"]["attachment_processing_status"] == "not_authorized_by_source_metadata_license"


def test_accepts_documented_json_list_shape_without_a_second_request():
    collector = MSITAnnouncementCollector(fetch_json=lambda *_args: [PAYLOAD["response"]["body"]["items"]["item"][0]])
    with patch.dict(os.environ, {"MSIT_ANNOUNCEMENT_API_KEY": "test-key"}, clear=False):
        result = collector.collect(_query(), limit=5)
    assert not result.errors
    assert [item.title for item in result.items] == ["2026 AI semiconductor R&D call"]


def test_accepts_json_array_response_envelope():
    response = [{"header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"}}, {"body": {"items": {"item": [PAYLOAD["response"]["body"]["items"]["item"][0]]}}}]
    collector = MSITAnnouncementCollector(fetch_json=lambda *_args: {"response": response})
    with patch.dict(os.environ, {"MSIT_ANNOUNCEMENT_API_KEY": "test-key"}, clear=False):
        result = collector.collect(_query(), limit=5)
    assert not result.errors
    assert len(result.items) == 1


def test_excludes_selection_results_instead_of_marking_them_open():
    payload = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": [
        {"subject": "2026 AI R&D 선정결과 공고", "viewUrl": "https://msit.example/result", "pressDt": "2026-11-08"}
    ]}}}}
    collector = MSITAnnouncementCollector(fetch_json=lambda *_args: payload)
    with patch.dict(os.environ, {"MSIT_ANNOUNCEMENT_API_KEY": "test-key"}, clear=False):
        result = collector.collect(_query("AI"), limit=5)
    assert result.items == []


def test_shared_snapshot_paginates_once_and_matches_multiple_interests():
    calls = []
    page_one = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": [
        {"subject": "정부 R&D 지원사업 공고", "viewUrl": "https://msit.example/a?nttSeqNo=1", "pressDt": "2026-11-08"}
    ]}}}}
    page_two = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": [
        {"subject": "국제공동연구 과제 공모", "viewUrl": "https://msit.example/b?nttSeqNo=2", "pressDt": "2026-11-07"}
    ]}}}}

    def fetch(url, *_args):
        calls.append(url)
        return page_one if parse_qs(urlparse(url).query)["pageNo"] == ["1"] else page_two

    collector = MSITAnnouncementCollector(fetch_json=fetch)
    query = [SourceQuery(source="msit_announcements", query="", params={
        "raw_interests": ["정부 R&D 지원사업", "국제공동연구"], "max_pages": 2, "page_size": 20,
    })]
    with patch.dict(os.environ, {"MSIT_ANNOUNCEMENT_API_KEY": "test-key"}, clear=False):
        result = collector.collect(query, limit=5)
    assert len(calls) == 2
    assert all(parse_qs(urlparse(url).query)["numOfRows"] == ["20"] for url in calls)
    assert {item.source_item_id for item in result.items} == {"1", "2"}
    assert "msit_records_received=2" in result.warnings


def test_diagnostics_distinguish_response_page_size_duplicate_and_missing_press_date():
    first = {"response": {"header": {"resultCode": "00"}, "body": {
        "numOfRows": 10, "totalCount": 30, "items": {"item": [
            {"subject": "AI R&D call", "viewUrl": "https://msit.example/a?nttSeqNo=1", "pressDt": "2026-11-08"},
            {"subject": "AI R&D call duplicate", "viewUrl": "https://msit.example/a?nttSeqNo=1", "pressDt": ""},
        ]},
    }}}
    second = {"response": {"header": {"resultCode": "00"}, "body": {
        "numOfRows": 10, "totalCount": 30, "items": {"item": [
            {"subject": "AI R&D follow-up", "viewUrl": "https://msit.example/b?nttSeqNo=2", "pressDt": "bad-date"},
        ]},
    }}}
    collector = MSITAnnouncementCollector(fetch_json=lambda url, *_args: first if "pageNo=1" in url else second)
    query = [SourceQuery(source="msit_announcements", query="AI", params={"raw_interest": "AI", "max_pages": 2, "page_size": 20})]
    with patch.dict(os.environ, {"MSIT_ANNOUNCEMENT_API_KEY": "test-key"}, clear=False):
        result = collector.collect(query, limit=20)
    assert "msit_page_1_requested_num_of_rows=20" in result.warnings
    assert "msit_page_1_response_num_of_rows=10" in result.warnings
    assert "msit_page_1_total_count=30" in result.warnings
    assert "msit_page_duplicates=1" in result.warnings
    assert "msit_press_dt_missing=1" in result.warnings
    assert "msit_press_dt_invalid=1" in result.warnings


def test_press_date_normalisation_accepts_documented_hyphen_and_dotted_forms_without_inventing_dates():
    assert MSITAnnouncementCollector._date("2026-11-08").startswith("2026-11-08")
    assert MSITAnnouncementCollector._date("2026.11.08.").startswith("2026-11-08")
    assert MSITAnnouncementCollector._date("20261108") is None

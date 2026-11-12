import os
from unittest.mock import patch

from src.sources.collectors.base import SourceQuery
from src.sources.collectors.mss_bizinfo import MSSBizInfoCollector
from src.sources.source_registry import source_availability


FIXTURE = """<?xml version='1.0' encoding='UTF-8'?>
<response><header><resultCode>00</resultCode><resultMsg>NORMAL_SERVICE</resultMsg></header><body><items>
 <item><pblancId>A-100</pblancId><title>2026 startup AI grant</title><writer>Ministry</writer><regDate>2026-11-01</regDate><updDate>2026.11.02</updDate><applyStartDate>20261103</applyStartDate><applyEndDate>2026-11-30</applyEndDate><supportTarget>early startup</supportTarget><keywords>startup, AI</keywords><detailUrl>https://official.example/A-100</detailUrl></item>
 <item><pblancId>B-200</pblancId><title>Marine fisheries notice</title><regDate>not-a-date</regDate></item>
</items></body></response>"""


def _query(interest="startup"):
    return [SourceQuery(source="mss_bizinfo", query=interest, params={"raw_interest": interest})]


def _collector(xml=FIXTURE):
    return MSSBizInfoCollector(fetch_text=lambda *_args: xml)


def test_normalises_15113297_fixture_without_inventing_fields():
    with patch.dict(os.environ, {"MSS_BIZINFO_API_KEY": "test-key", "MSS_BIZINFO_API_URL": "https://official.example/api"}, clear=False):
        result = _collector().collect(_query(), limit=5)
    assert not result.errors
    assert len(result.items) == 1
    item = result.item_dicts()[0]
    assert item["source_item_id"] == "A-100"
    assert item["title"] == "2026 startup AI grant"
    assert item["author"] == "Ministry"
    assert item["published_at"].startswith("2026-11-01")
    assert item["metrics_json"]["announcement_modified_at"].startswith("2026-11-02")
    assert item["metrics_json"]["application_end_at"].startswith("2026-11-30")
    assert item["raw_json"]["service_id"] == "15113297"
    # The next one-shot diagnostic can distinguish an issued-schema mismatch
    # without preserving any response values.
    assert "mss_schema_title_present=2" in result.warnings
    assert "mss_schema_application_end_at_present=1" in result.warnings
    assert "mss_schema_source_url_present=1" in result.warnings


def test_missing_title_and_invalid_dates_are_not_fabricated():
    xml = """<response><header><resultCode>00</resultCode></header><body><items>
      <item><pblancId>no-title</pblancId></item>
      <item><pblancId>bad-date</pblancId><title>startup notice</title><regDate>tomorrow-ish</regDate></item>
    </items></body></response>"""
    with patch.dict(os.environ, {"MSS_BIZINFO_API_KEY": "test-key", "MSS_BIZINFO_API_URL": "https://official.example/api"}, clear=False):
        result = _collector(xml).collect(_query(), limit=5)
    assert len(result.items) == 1
    assert result.items[0].published_at is None
    assert result.items[0].metrics_json["announcement_published_at"] is None


def test_deduplicates_by_official_announcement_id():
    # Use a concise explicit duplicate fixture to avoid making URL/title part
    # of an accidental identity.
    xml = """<response><header><resultCode>00</resultCode></header><body><items>
    <item><pblancId>A-100</pblancId><title>startup grant</title></item>
    <item><pblancId>A-100</pblancId><title>startup grant corrected</title></item>
    </items></body></response>"""
    with patch.dict(os.environ, {"MSS_BIZINFO_API_KEY": "test-key", "MSS_BIZINFO_API_URL": "https://official.example/api"}, clear=False):
        result = _collector(xml).collect(_query(), limit=5)
    assert len(result.items) == 1


def test_xml_auth_and_network_failures_do_not_retry():
    bad_xml = _collector("<response>")
    with patch.dict(os.environ, {"MSS_BIZINFO_API_KEY": "test-key", "MSS_BIZINFO_API_URL": "https://official.example/api"}, clear=False):
        assert "invalid XML" in bad_xml.collect(_query(), limit=5).errors[0]

    auth_xml = "<response><header><resultCode>30</resultCode><resultMsg>INVALID KEY</resultMsg></header></response>"
    with patch.dict(os.environ, {"MSS_BIZINFO_API_KEY": "test-key", "MSS_BIZINFO_API_URL": "https://official.example/api"}, clear=False):
        assert "API error 30" in _collector(auth_xml).collect(_query(), limit=5).errors[0]

    calls = []
    collector = MSSBizInfoCollector(fetch_text=lambda *_args: calls.append(1) or (_ for _ in ()).throw(OSError("offline")))
    with patch.dict(os.environ, {"MSS_BIZINFO_API_KEY": "test-key", "MSS_BIZINFO_API_URL": "https://official.example/api"}, clear=False):
        assert "network request failed" in collector.collect(_query(), limit=5).errors[0]
    assert len(calls) == 1


def test_missing_key_never_calls_network_and_source_stays_permission_review():
    calls = []
    collector = MSSBizInfoCollector(fetch_text=lambda *_args: calls.append(1) or FIXTURE)
    with patch.dict(os.environ, {"MSS_BIZINFO_API_KEY": "", "MSS_BIZINFO_API_URL": ""}, clear=False):
        result = collector.collect(_query(), limit=5)
    assert result.errors == ["MSS_BIZINFO_API_KEY is required; no request was made."]
    assert not calls
    assert source_availability("mss_bizinfo", {})["state"] == "permission_review"

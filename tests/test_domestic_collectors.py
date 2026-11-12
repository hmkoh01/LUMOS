import io
import os
import zipfile
from unittest.mock import patch

from src.sources.collectors.base import SourceQuery
from src.sources.collectors.kopis import KOPISCollector
from src.sources.collectors.opendart import OpenDARTCollector
from src.sources import opendart_corporations
from src.sources.opendart_corporations import CorporationCodeCache, refresh_shared_corporation_cache
from src.sources.collectors.schema_pending import PublicInstitutionJobsCollector, PublicServiceJobsCollector, SeoulCultureEventsCollector, YouthCenterPolicyCollector
from src.sources.collectors.work24 import Work24Collector
from src.sources.collector_registry import CollectorRegistry
from src.sources.router import SourceRouter
from src.sources.source_registry import source_availability, source_usage_permission


def test_work24_normalises_documented_xml_and_excludes_ended_postings():
    xml = """<wantedRoot><wanted><wantedAuthNo>W-1</wantedAuthNo><company>Example</company><title>Junior developer internship</title><career>N</career><region>Seoul</region><regDt>20261101</regDt><closeDt>20991231</closeDt><wantedInfoUrl>https://work24.example/W-1</wantedInfoUrl><infoSvc>VALIDATION</infoSvc></wanted><wanted><wantedAuthNo>W-1</wantedAuthNo><title>duplicate</title></wanted><wanted><wantedAuthNo>W-2</wantedAuthNo><title>Old job</title><regDt>20200101</regDt><closeDt>20200102</closeDt></wanted></wantedRoot>"""
    collector = Work24Collector(fetch_text=lambda *_: xml)
    with patch.dict(os.environ, {"WORK24_API_KEY": "test"}, clear=False):
        result = collector.collect([SourceQuery(source="employment24", query="", params={})], 10)
    assert len(result.items) == 1
    item = result.item_dicts()[0]
    assert item["source_item_id"] == "W-1"
    assert item["metrics_json"]["application_window_status"] == "ongoing"
    assert item["raw_json"]["information_provider"] == "VALIDATION"


def test_work24_missing_key_and_invalid_xml_never_retry():
    calls = []
    collector = Work24Collector(fetch_text=lambda *_: calls.append(1) or "<wantedRoot>")
    with patch.dict(os.environ, {"WORK24_API_KEY": ""}, clear=False):
        assert collector.collect([], 1).errors[0].startswith("WORK24_API_KEY")
    assert not calls
    with patch.dict(os.environ, {"WORK24_API_KEY": "test"}, clear=False):
        assert "invalid XML" in collector.collect([], 1).errors[0]
    assert len(calls) == 1


def _corporation_zip(*rows):
    xml = "<result>" + "".join(
        "<list><corp_code>{}</corp_code><corp_name>{}</corp_name><stock_code>{}</stock_code><modify_date>20261109</modify_date></list>".format(*row)
        for row in rows
    ) + "</result>"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("CORPCODE.xml", xml)
    return buffer.getvalue()


def test_opendart_uses_verified_corp_code_receipt_date_and_official_viewer_link_only():
    payload = {"status": "000", "list": [
        {"rcept_no": "20261109000001", "report_nm": "Major management disclosure", "corp_name": "Example Corp", "corp_code": "00123456", "corp_cls": "K", "flr_nm": "Example Corp", "rcept_dt": "20261109"},
        {"rcept_no": "20261109000002", "report_nm": "Other company filing", "corp_name": "Other Corp", "corp_code": "00999999", "rcept_dt": "20261109"},
    ]}
    cache = CorporationCodeCache()
    cache.replace_from_zip(_corporation_zip(("00123456", "Example Corp", "123456")))
    requested = []
    collector = OpenDARTCollector(fetch_json=lambda url, *_: (requested.append(url), payload)[1], corporation_cache=cache)
    with patch.dict(os.environ, {"OPENDART_API_KEY": "test"}, clear=False):
        result = collector.collect([SourceQuery(source="opendart", query="Example Corp", params={"company_name": "Example Corp", "bgn_de": "20261101", "end_de": "20261109"})], 10)
    assert len(result.items) == 1
    assert "corp_code=00123456" in requested[0]
    item = result.item_dicts()[0]
    assert item["published_at"].startswith("2026-11-09")
    assert item["metrics_json"]["content_kind"] == "corporate_disclosure"
    assert "rcpNo=20261109000001" in item["url"]


def test_opendart_provider_error_and_missing_date_range_do_not_create_items():
    cache = CorporationCodeCache()
    cache.replace_from_zip(_corporation_zip(("00123456", "Example Corp", "123456")))
    collector = OpenDARTCollector(fetch_json=lambda *_: {"status": "013", "message": "no data"}, corporation_cache=cache)
    with patch.dict(os.environ, {"OPENDART_API_KEY": "test"}, clear=False):
        assert "bgn_de and end_de" in collector.collect([], 1).errors[0]
        result = collector.collect([SourceQuery(source="opendart", query="Example Corp", params={"company_name": "Example Corp", "bgn_de": "20261101", "end_de": "20261109"})], 1)
    assert "API error 013" in result.errors[0]


def test_opendart_blocks_ambiguous_or_unknown_company_before_list_request():
    calls = []
    cache = CorporationCodeCache()
    cache.replace_from_zip(
        _corporation_zip(("00123456", "Same Name", "123456"), ("00999999", "Same Name", "999999"))
    )
    collector = OpenDARTCollector(fetch_json=lambda *_: calls.append(1), corporation_cache=cache)
    with patch.dict(os.environ, {"OPENDART_API_KEY": "test"}, clear=False):
        ambiguous = collector.collect([SourceQuery(source="opendart", query="Same Name", params={"bgn_de": "20261101", "end_de": "20261109"})], 10)
        missing = collector.collect([SourceQuery(source="opendart", query="Missing Corp", params={"bgn_de": "20261101", "end_de": "20261109"})], 10)
    assert ambiguous.attempted is False and ambiguous.warnings == ["opendart_corp_code_ambiguous"]
    assert missing.attempted is False and missing.warnings == ["opendart_corp_code_not_found"]
    assert calls == []


def test_opendart_corporation_directory_refreshes_the_shared_cache_once(monkeypatch):
    shared = CorporationCodeCache()
    monkeypatch.setattr(opendart_corporations, "SHARED_CORPORATION_CODE_CACHE", shared)
    calls = []
    count = refresh_shared_corporation_cache(
        "test-key",
        fetch_bytes=lambda url, *_: calls.append(url) or _corporation_zip(("00123456", "Example Corp", "123456")),
    )
    assert count == 1
    assert len(calls) == 1
    assert "corpCode.xml" in calls[0]
    assert shared.resolve("Example Corp").record.corp_code == "00123456"


def test_opendart_empty_and_wrong_corporation_rows_are_not_recommended_without_ai_calls():
    cache = CorporationCodeCache()
    cache.replace_from_zip(_corporation_zip(("00123456", "Example Corp", "123456")))
    payload = {"status": "000", "list": [{
        "rcept_no": "20261109000009", "report_nm": "Other filing", "corp_name": "Other Corp", "corp_code": "00999999", "rcept_dt": "20261109",
    }]}
    collector = OpenDARTCollector(fetch_json=lambda *_: payload, corporation_cache=cache)
    with patch.dict(os.environ, {"OPENDART_API_KEY": "test"}, clear=False), \
         patch("src.signals.translation.translate", side_effect=AssertionError("translation must not run")):
        result = collector.collect([SourceQuery(source="opendart", query="Example Corp", params={"bgn_de": "20261101", "end_de": "20261109"})], 10)
    assert result.errors == []
    assert result.items == []


def test_kopis_normalises_documented_fields_and_maps_only_valid_ids_to_the_official_web_detail_page():
    xml = """<dbs><db><mt20id>PF301231</mt20id><prfnm>City music performance</prfnm><prfpdfrom>2099.12.01</prfpdfrom><prfpdto>2099.12.31</prfpdto><fcltynm>City Hall</fcltynm><area>Seoul</area><genrenm>Music</genrenm><poster>https://image.example/x.jpg</poster></db><db><mt20id>PF-2</mt20id><prfnm>Invalid ID</prfnm><prfpdfrom>2099.12.01</prfpdfrom><prfpdto>2099.12.31</prfpdto></db><db><mt20id>PF2</mt20id><prfnm>Ended</prfnm><prfpdfrom>2020.01.01</prfpdfrom><prfpdto>2020.01.02</prfpdto></db></dbs>"""
    collector = KOPISCollector(fetch_text=lambda *_: xml)
    with patch.dict(os.environ, {"KOPIS_API_KEY": "test"}, clear=False):
        result = collector.collect([SourceQuery(source="kopis", query="", params={"stdate": "20261101", "eddate": "20261130"})], 10)
    assert len(result.items) == 2
    item, invalid_id = result.item_dicts()
    assert item["url"] == "https://kopis.or.kr/por/db/pblprfr/pblprfrView.do?mt20Id=PF301231"
    assert item["raw_json"]["poster_collected"] is False
    assert item["metrics_json"]["source_url_status"] == "official_web_detail_pattern"
    assert item["metrics_json"]["official_detail_content_verified"] is False
    assert invalid_id["url"] == ""
    assert invalid_id["metrics_json"]["source_url_status"] == "invalid_performance_id"


def _schema_config():
    return {"schema_confirmed": True, "api_url": "https://official.example/api", "records_path": ["response", "items"], "field_map": {"id": "id", "title": "title", "source_url": "url", "start_at": "start", "end_at": "end", "region": "region", "target": "target", "job_type": "type", "published_at": "published", "publisher": "publisher"}}


def test_schema_pending_collectors_block_without_issued_schema_and_normalise_fixture_after_confirmation():
    payload = {"response": {"items": [
        {"id": "A", "title": "Youth housing support", "url": "https://official.example/A", "start": "20990101", "end": "20991231", "region": "Seoul", "target": "young people", "type": "housing"},
        {"id": "B", "title": "Ended", "url": "https://official.example/B", "start": "20200101", "end": "20200102"},
        {"id": "C", "title": "No verified link", "url": "", "start": "not-a-date", "end": ""},
    ]}}
    classes = (PublicInstitutionJobsCollector, PublicServiceJobsCollector, YouthCenterPolicyCollector, SeoulCultureEventsCollector)
    for klass in classes:
        collector = klass(fetch_json=lambda *_: payload)
        blocked = collector.collect([SourceQuery(source=collector.source_id, query="", params={})], 10)
        assert blocked.attempted is False and "schema_pending" in blocked.warnings[0]
        with patch.dict(os.environ, {collector.env_key: "test"}, clear=False):
            result = collector.collect([SourceQuery(source=collector.source_id, query="", params=_schema_config())], 10)
        assert [item.source_item_id for item in result.items] == ["A", "C"]
        assert result.items[0].metrics_json["status"] == "upcoming"
        assert result.items[1].url == ""
        assert result.items[1].metrics_json["status"] == "unknown"


def test_new_sources_are_registered_but_not_available_and_no_github_hn_fallback_exists():
    registry = CollectorRegistry()
    for source in ("public_institution_jobs", "public_service_jobs", "youthcenter_policy", "seoul_culture_events", "employment24", "opendart", "kopis", "mss_support_program"):
        assert registry.support_status(source, mode="live") == "implemented"
        assert source_availability(source, {})["state"] == "permission_review"
    routes = SourceRouter().plan({}, {}, [], [{"keyword": "junior developer hiring", "status": "active"}], source_configs=[])
    assert routes == []
    from src.sources.router import ROUTING_RULES
    assert ROUTING_RULES["CAREER"][:3] == ["public_institution_jobs", "public_service_jobs", "employment24"]
    assert ROUTING_RULES["CULTURE_TRAVEL_EVENT"][:3] == ["seoul_culture_events", "kopis", "tourapi"]
    assert ROUTING_RULES["ECONOMY_FINANCE"][0] == "opendart"


def test_scope_permissions_do_not_override_the_global_permission_review_gate():
    assert source_usage_permission("tourapi", "metadata_display")["state"] == "allowed_with_attribution"
    assert source_usage_permission("tourapi", "llm_processing")["state"] == "not_granted"
    assert source_usage_permission("opendart", "metadata_display")["state"] == "allowed_with_source_link"
    assert source_usage_permission("opendart", "llm_processing")["state"] == "permission_review"
    # Scope approval records are not a shortcut around source activation.
    assert source_availability("tourapi", {"usage_status": "approved"})["state"] == "permission_review"
    assert source_availability("opendart", {"usage_status": "approved"})["state"] == "permission_review"

import os
from unittest.mock import patch

from src.sources.collectors.base import SourceQuery
from src.sources.collectors.mss_support_program import MSSSupportProgramCollector
from src.sources.collector_registry import CollectorRegistry
from src.sources.source_registry import SOURCE_CAPABILITIES, source_availability


def _query(interest=""):
    return SourceQuery(source="mss_support_program", query=interest, params={"sprtBizYr": "2026", "raw_interest": interest})


PAYLOAD = {"resultCode": "00", "resultMsg": "normal", "numOfRows": 10, "pageNo": 1, "totalCount": 4, "item": [
    {"sprtBizCd": "P-1", "sprtBizNm": "Startup commercialisation support", "sprtBizPurpose": "commercialise early-stage technology", "sprtBizTrgtNm": "early startup", "sprtBizCtpvNm": "Seoul", "operInstNm": "Official Agency", "progrsSttusNm": "recruiting", "rcritBgngYmd": "20990101", "rcritEndYmd": "20991231", "sprtBizUrl": "https://official.example/P-1", "sprtBizYr": "2026", "sprtBizTyNm": "commercialisation", "sprtBizCg1Nm": "startup"},
    {"sprtBizCd": "P-1", "sprtBizNm": "duplicate", "rcritBgngYmd": "20990101", "rcritEndYmd": "20991231"},
    {"sprtBizCd": "P-2", "sprtBizNm": "selection result", "progrsSttusNm": "selection result", "rcritBgngYmd": "20990101", "rcritEndYmd": "20991231"},
    {"sprtBizCd": "P-3", "sprtBizNm": "Unknown window", "rcritBgngYmd": "bad-date", "sprtBizUrl": ""},
]}


def test_normalises_official_schema_item_array_and_rejects_results():
    collector = MSSSupportProgramCollector(fetch_json=lambda *_args: PAYLOAD)
    with patch.dict(os.environ, {"PUBLIC_DATA_PORTAL_SERVICE_KEY": "test-key"}, clear=False):
        result = collector.collect([_query()], 10)
    assert [item.source_item_id for item in result.items] == ["P-1", "P-3"]
    first, unknown = result.item_dicts()
    assert first["metrics_json"]["support_target"] == "early startup"
    assert first["metrics_json"]["application_window_status"] == "upcoming"
    assert unknown["metrics_json"]["application_window_status"] == "unknown"
    assert unknown["url"] == ""
    assert "mss_support_rejected_status=1" in result.warnings
    assert "mss_support_response_classification=schema_valid_unverified_code" in result.warnings


def test_accepts_single_item_and_blocks_missing_year_or_key_without_network():
    calls = []
    collector = MSSSupportProgramCollector(fetch_json=lambda *_args: calls.append(1) or {**PAYLOAD, "item": PAYLOAD["item"][0]})
    with patch.dict(os.environ, {"PUBLIC_DATA_PORTAL_SERVICE_KEY": "test-key"}, clear=False):
        result = collector.collect([_query()], 10)
        assert len(result.items) == 1
        assert "sprtBizYr" in collector._url("x", "2026", {}, 10)
        missing_year = collector.collect([SourceQuery(source="mss_support_program", query="", params={})], 10)
    assert "sprtBizYr is required" in missing_year.errors[0]
    with patch.dict(os.environ, {"PUBLIC_DATA_PORTAL_SERVICE_KEY": "", "MSS_SUPPORT_PROGRAM_API_KEY": ""}, clear=False):
        missing_key = collector.collect([_query()], 10)
    assert "PUBLIC_DATA_PORTAL_SERVICE_KEY" in missing_key.errors[0]
    assert len(calls) == 1


def test_schema_is_official_but_source_remains_permission_review_and_no_fallback_route():
    assert CollectorRegistry().support_status("mss_support_program", mode="live") == "implemented"
    assert SOURCE_CAPABILITIES["mss_support_program"]["schema_status"] == "official"
    assert source_availability("mss_support_program", {})["state"] == "permission_review"

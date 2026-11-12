import os
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from src.sources.collectors.base import SourceQuery
from src.sources.collectors.tourapi import TourAPIFestivalCollector
from src.sources.source_registry import source_availability


def _payload(items):
    return {"response": {"header": {"resultCode": "000"}, "body": {"items": {"item": items}}}}


def test_tourapi_four_digit_normal_success_code_is_not_rejected(monkeypatch):
    monkeypatch.setattr(TourAPIFestivalCollector, "_today_kst", staticmethod(lambda: __import__("datetime").date(2026, 11, 8)))
    payload = {"response": {"header": {"resultCode": "0000"}, "body": {"items": {"item": [{
        "contentid": "43", "title": "Festival", "eventstartdate": "20261110", "eventenddate": "20261112",
    }]}}}}
    collector = TourAPIFestivalCollector(fetch_json=lambda *_args: payload)
    with patch.dict(os.environ, {"TOURAPI_SERVICE_KEY": "test-key"}, clear=False):
        result = collector.collect([SourceQuery(source="tourapi", query="", params={})], 10)
    assert not result.errors
    assert len(result.items) == 1


def test_tourapi_fixture_keeps_only_schedule_metadata_and_never_images(monkeypatch):
    monkeypatch.setattr(TourAPIFestivalCollector, "_today_kst", staticmethod(lambda: __import__("datetime").date(2026, 11, 8)))
    payload = _payload([{
        "contentid": "42", "title": "\uc9c0\uc5ed \ucd95\uc81c", "eventstartdate": "20261110", "eventenddate": "20261112",
        "addr1": "\uc11c\uc6b8\uc2dc", "addr2": "\uc911\uad6c", "firstimage": "https://image.example/test.jpg",
    }])
    collector = TourAPIFestivalCollector(fetch_json=lambda *_args: payload)
    with patch.dict(os.environ, {"TOURAPI_SERVICE_KEY": "test-key"}, clear=False):
        result = collector.collect([SourceQuery(source="tourapi", query="", params={"event_start_date": "20261101"})], 20)
    assert len(result.items) == 1
    item = result.items[0]
    assert item.metrics_json["event_status"] == "upcoming"
    assert item.metrics_json["venue"] == "\uc11c\uc6b8\uc2dc \uc911\uad6c"
    assert item.metrics_json["region"] == "서울시"
    assert item.metrics_json["image_collected"] is False
    assert "firstimage" not in item.raw_json


def test_tourapi_missing_key_never_requests_network():
    calls = []
    collector = TourAPIFestivalCollector(fetch_json=lambda *_args: calls.append(1) or {})
    with patch.dict(os.environ, {"TOURAPI_SERVICE_KEY": ""}, clear=False):
        result = collector.collect([], 1)
    assert result.errors == ["TOURAPI_SERVICE_KEY is required; no request was made."]
    assert calls == []


def test_tourapi_code_exists_but_registry_keeps_it_in_permission_review(monkeypatch):
    monkeypatch.setenv("TOURAPI_SERVICE_KEY", "test-key")
    state = source_availability("tourapi", {})
    assert state["state"] == "permission_review"
    assert state["available"] is False
    assert state["capabilities"]["service_id"] == "15101578"


def test_tourapi_http_error_keeps_provider_code_without_leaking_request_url(monkeypatch):
    error = HTTPError(
        "https://apis.data.go.kr/B551011/KorService2/searchFestival2?serviceKey=secret-value",
        403, "Forbidden", {}, BytesIO(b'{"response":{"header":{"resultCode":"30","resultMsg":"SERVICE ACCESS DENIED"}}}'),
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(error))
    try:
        TourAPIFestivalCollector._fetch_json("https://apis.data.go.kr/B551011/KorService2/searchFestival2?serviceKey=secret-value", 1, {})
    except RuntimeError as exc:
        detail = str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected HTTP error")
    assert "HTTP 403" in detail
    assert "provider_code=30" in detail
    assert "SERVICE ACCESS DENIED" in detail
    assert "secret-value" not in detail
    assert "searchFestival2" not in detail

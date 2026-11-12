from datetime import datetime, timedelta, timezone

import pytest

from src.engine.queue.sqlite_store import SQLiteQueueStore
from src.sources import opendart_corporations
from src.sources.opendart_corporations import QueueCorporationCodeCache, refresh_queue_corporation_cache


def _records():
    return [{
        "normalized_name": "example corp", "corp_code": "00123456", "corp_name": "Example Corp",
        "stock_code": "123456", "modify_date": "20261110",
    }]


def test_durable_directory_is_shared_between_independent_worker_stores(tmp_path):
    path = tmp_path / "queue.sqlite"
    writer = SQLiteQueueStore(path)
    reader = SQLiteQueueStore(path)
    writer.replace_opendart_corporation_directory(_records())

    resolution = QueueCorporationCodeCache(reader).resolve("Example Corp")
    assert resolution.state == "resolved"
    assert resolution.record and resolution.record.corp_code == "00123456"


def test_stale_or_failed_directory_is_withheld_without_erasing_last_good_cache(tmp_path):
    queue = SQLiteQueueStore(tmp_path / "queue.sqlite")
    old = (datetime.now(timezone.utc) - timedelta(days=8)).replace(microsecond=0).isoformat()
    queue.replace_opendart_corporation_directory(_records(), refreshed_at=old)
    assert QueueCorporationCodeCache(queue, max_age_seconds=7 * 24 * 3600).resolve("Example Corp").state == "cache_unavailable"
    with pytest.raises(ValueError):
        queue.replace_opendart_corporation_directory([])
    # A failed replacement leaves the verified record intact; freshness is
    # still conservative until the next successful refresh.
    assert queue.resolve_opendart_corporation("example corp", max_age_seconds=99 * 24 * 3600)["state"] == "resolved"


def test_durable_refresh_uses_one_shared_daily_request_slot(tmp_path, monkeypatch):
    queue_a = SQLiteQueueStore(tmp_path / "queue.sqlite")
    queue_b = SQLiteQueueStore(tmp_path / "queue.sqlite")
    monkeypatch.setattr(opendart_corporations, "parse_corporation_zip", lambda _: iter([
        opendart_corporations.CorporationRecord("00123456", "Example Corp", "123456", "20261110"),
    ]))
    calls = []
    assert refresh_queue_corporation_cache(
        queue_a, "test-key", fetch_bytes=lambda *_: calls.append(1) or b"fixture",
    ) == 1
    with pytest.raises(RuntimeError, match="request_budget_exhausted"):
        refresh_queue_corporation_cache(queue_b, "test-key", fetch_bytes=lambda *_: calls.append(1) or b"fixture")
    assert calls == [1]


def test_exact_stock_code_resolution_requires_one_shared_official_record(tmp_path):
    queue = SQLiteQueueStore(tmp_path / "queue.sqlite")
    queue.replace_opendart_corporation_directory(_records())
    directory = QueueCorporationCodeCache(queue)
    assert directory.resolve_stock_code("123456").state == "resolved"
    assert directory.resolve_stock_code("999999").state == "not_found"
    queue.replace_opendart_corporation_directory([
        {"normalized_name": "one", "corp_code": "00123456", "corp_name": "One", "stock_code": "777777", "modify_date": "20261110"},
        {"normalized_name": "two", "corp_code": "00987654", "corp_name": "Two", "stock_code": "777777", "modify_date": "20261110"},
    ])
    assert QueueCorporationCodeCache(queue).resolve_stock_code("777777").state == "ambiguous"


def test_opendart_uses_one_utc_day_budget_across_kst_midnight_boundary(tmp_path):
    """06:30 KST is still the previous UTC date, so it cannot reset quota."""
    queue = SQLiteQueueStore(tmp_path / "queue.sqlite")
    utc_day = "2026-11-10"
    assert queue.reserve_source_request("opendart", utc_day, 2)
    assert queue.reserve_source_request("opendart", utc_day, 2)
    assert not queue.reserve_source_request("opendart", utc_day, 2)
    assert queue.get_source_request_usage("opendart", utc_day) == 2

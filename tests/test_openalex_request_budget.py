from src.engine.queue.sqlite_store import SQLiteQueueStore


def test_openalex_daily_cap_is_shared_by_independent_queue_store_instances(tmp_path):
    db_path = tmp_path / "queue.db"
    worker_a = SQLiteQueueStore(db_path)
    worker_b = SQLiteQueueStore(db_path)

    assert worker_a.reserve_source_request("openalex", "2026-11-08", 2)
    assert worker_b.reserve_source_request("openalex", "2026-11-08", 2)
    assert not worker_a.reserve_source_request("openalex", "2026-11-08", 2)
    assert worker_b.get_source_request_usage("openalex", "2026-11-08") == 2


def test_openalex_daily_cap_resets_for_a_new_kst_date(tmp_path):
    store = SQLiteQueueStore(tmp_path / "queue.db")
    assert store.reserve_source_request("openalex", "2026-11-08", 1)
    assert not store.reserve_source_request("openalex", "2026-11-08", 1)
    assert store.reserve_source_request("openalex", "2026-11-09", 1)


def test_zero_cap_blocks_before_any_request_is_reserved(tmp_path):
    store = SQLiteQueueStore(tmp_path / "queue.db")
    assert not store.reserve_source_request("openalex", "2026-11-08", 0)
    assert store.get_source_request_usage("openalex", "2026-11-08") == 0

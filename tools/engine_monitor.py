"""Read-only aggregate health report for an Engine v2 SQLite deployment.

It deliberately emits no prompts, source content, user identifiers, API keys,
or provider error bodies.  It is suitable for a Railway shell/cron check.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.engine.llm.structured_cache import StructuredBriefingCache
from src.engine.queue.sqlite_store import SQLiteQueueStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-db", type=Path, required=True)
    parser.add_argument("--queue-db", type=Path, required=True)
    args = parser.parse_args()
    if not args.cache_db.exists() or not args.queue_db.exists():
        raise SystemExit("cache-db and queue-db must both exist")
    cache = StructuredBriefingCache(args.cache_db)
    queue = SQLiteQueueStore(args.queue_db)
    try:
        print(json.dumps({"cache_metrics": cache.metric_summary(), "queue": queue.monitoring_summary()}, indent=2))
    finally:
        cache.close()
        queue.close()


if __name__ == "__main__":
    main()

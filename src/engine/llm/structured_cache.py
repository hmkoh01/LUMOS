"""Persistent, versioned caches for validated structured briefing artifacts."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS engine_content_artifact_cache (
    cache_key TEXT PRIMARY KEY, content_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS engine_personalization_cache (
    cache_key TEXT PRIMARY KEY, personalization_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS engine_metric_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, metric TEXT NOT NULL, value REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class StructuredBriefingCache:
    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def get_content(self, key: str) -> Optional[Dict[str, Any]]:
        return self._get("engine_content_artifact_cache", "content_json", key)

    def put_content(self, key: str, value: Dict[str, Any]) -> None:
        self._put("engine_content_artifact_cache", "content_json", key, value)

    def get_personalization(self, key: str) -> Optional[Dict[str, Any]]:
        return self._get("engine_personalization_cache", "personalization_json", key)

    def put_personalization(self, key: str, value: Dict[str, Any]) -> None:
        self._put("engine_personalization_cache", "personalization_json", key, value)

    def _get(self, table: str, field: str, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(f"SELECT {field} FROM {table} WHERE cache_key = ?", (key,)).fetchone()
        return json.loads(row[field]) if row else None

    def _put(self, table: str, field: str, key: str, value: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                f"INSERT INTO {table} (cache_key, {field}) VALUES (?, ?) "
                f"ON CONFLICT(cache_key) DO UPDATE SET {field}=excluded.{field}",
                (key, json.dumps(value, ensure_ascii=False)),
            )
            self._conn.commit()

    def purge_older_than(self, days: int) -> Dict[str, int]:
        """Remove stale artifacts without inspecting their content."""
        if days < 1:
            raise ValueError("cache retention must be at least one day")
        result = {}
        with self._lock:
            for table in ("engine_content_artifact_cache", "engine_personalization_cache"):
                cursor = self._conn.execute(
                    f"DELETE FROM {table} WHERE created_at < datetime('now', ?)", (f"-{days} days",)
                )
                result[table] = cursor.rowcount
            self._conn.commit()
        return result

    def record_metric(self, metric: str, value: float = 1.0) -> None:
        """Store aggregate-only telemetry; never accepts prompts or user data."""
        with self._lock:
            self._conn.execute("INSERT INTO engine_metric_events (metric, value) VALUES (?, ?)", (metric, value))
            self._conn.commit()

    def metric_summary(self) -> Dict[str, float]:
        with self._lock:
            rows = self._conn.execute("SELECT metric, SUM(value) AS total FROM engine_metric_events GROUP BY metric").fetchall()
        return {row["metric"]: row["total"] for row in rows}

    def close(self) -> None:
        with self._lock:
            self._conn.close()

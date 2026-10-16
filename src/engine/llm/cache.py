"""Shared Korean briefing cache.

A single source item's Korean title/summary/facts are generated once
and reused across all users whose briefing includes that item.
Displaying a cached briefing does NOT count as LLM usage.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.engine.models import KoreanBriefing


_SCHEMA = """
CREATE TABLE IF NOT EXISTS briefing_cache (
    dedupe_key          TEXT PRIMARY KEY,
    display_title_ko    TEXT NOT NULL DEFAULT '',
    headline_summary_ko TEXT NOT NULL DEFAULT '',
    key_facts_ko_json   TEXT NOT NULL DEFAULT '[]',
    generated_by        TEXT NOT NULL DEFAULT 'rule',
    confidence          REAL NOT NULL DEFAULT 1.0,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at          TEXT
);
"""


class BriefingCache:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or ":memory:")
        self._shared_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            self._shared_conn = self._make_conn()
        self._init_schema()

    def _make_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _connect(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        return self._make_conn()

    def _init_schema(self) -> None:
        conn = self._connect()
        conn.execute(_SCHEMA)
        conn.commit()

    def get(self, dedupe_key: str) -> Optional[KoreanBriefing]:
        """Fetch a cached briefing.  Returns None if missing or expired."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM briefing_cache WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
            if row is None:
                return None
            # Check expiry
            expires = row["expires_at"]
            if expires:
                try:
                    exp_dt = datetime.fromisoformat(expires)
                    if exp_dt < datetime.now(timezone.utc):
                        return None
                except ValueError:
                    pass
            return KoreanBriefing(
                dedupe_key=row["dedupe_key"],
                display_title_ko=row["display_title_ko"],
                headline_summary_ko=row["headline_summary_ko"],
                key_facts_ko=json.loads(row["key_facts_ko_json"] or "[]"),
                generated_by=row["generated_by"],
                confidence=row["confidence"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
            )

    def put(self, briefing: KoreanBriefing) -> None:
        """Upsert a cached briefing."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO briefing_cache
                   (dedupe_key, display_title_ko, headline_summary_ko,
                    key_facts_ko_json, generated_by, confidence, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                   ON CONFLICT(dedupe_key) DO UPDATE SET
                       display_title_ko = excluded.display_title_ko,
                       headline_summary_ko = excluded.headline_summary_ko,
                       key_facts_ko_json = excluded.key_facts_ko_json,
                       generated_by = excluded.generated_by,
                       confidence = excluded.confidence,
                       expires_at = excluded.expires_at""",
                (
                    briefing.dedupe_key,
                    briefing.display_title_ko,
                    briefing.headline_summary_ko,
                    json.dumps(briefing.key_facts_ko, ensure_ascii=False),
                    briefing.generated_by,
                    briefing.confidence,
                    briefing.expires_at,
                ),
            )
            conn.commit()

    def get_many(self, dedupe_keys: List[str]) -> Dict[str, KoreanBriefing]:
        """Batch fetch cached briefings.  Returns a dict keyed by dedupe_key."""
        if not dedupe_keys:
            return {}
        result: Dict[str, KoreanBriefing] = {}
        for key in dedupe_keys:
            cached = self.get(key)
            if cached is not None:
                result[key] = cached
        return result

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM briefing_cache").fetchone()[0]

    def purge_expired(self) -> int:
        """Remove expired entries.  Returns count deleted."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM briefing_cache WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            conn.commit()
            return cursor.rowcount

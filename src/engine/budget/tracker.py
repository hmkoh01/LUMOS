"""Usage tracking and budget enforcement.

Tracks per-user and global usage.  When a hard cap is reached, new
external jobs are blocked but cached content continues to be served.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.engine.config import BudgetConfig, EngineConfig
from src.engine.models import UsageRecord


_SCHEMA = """
CREATE TABLE IF NOT EXISTS engine_usage (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL DEFAULT 0,
    event_type      TEXT    NOT NULL,
    tokens_used     INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
    metadata_json   TEXT    NOT NULL DEFAULT '{}',
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_engine_usage_user_date
    ON engine_usage (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_engine_usage_type_date
    ON engine_usage (event_type, created_at);
"""


class BudgetTracker:
    def __init__(self, config: BudgetConfig, db_path: Optional[Path] = None):
        self.config = config
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
        for stmt in _SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()

    def record(self, record: UsageRecord) -> int:
        """Record a usage event.  Returns the event ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO engine_usage
                   (user_id, event_type, tokens_used, estimated_cost_usd, metadata_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    record.user_id,
                    record.event_type,
                    record.tokens_used,
                    record.estimated_cost_usd,
                    json.dumps(record.metadata, ensure_ascii=False),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def _sum_today(self, event_type: Optional[str] = None, user_id: Optional[int] = None) -> Dict[str, float]:
        # Use SQLite-compatible format (YYYY-MM-DD HH:MM:SS) to match CURRENT_TIMESTAMP
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        clauses = ["created_at >= ?"]
        params: list = [today_start]
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        where = " AND ".join(clauses)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT COALESCE(SUM(tokens_used), 0) as tokens, "
                f"COALESCE(SUM(estimated_cost_usd), 0.0) as cost, "
                f"COUNT(*) as count "
                f"FROM engine_usage WHERE {where}",
                params,
            ).fetchone()
            return {"tokens": row["tokens"], "cost": row["cost"], "count": row["count"]}

    def _sum_month(self) -> Dict[str, float]:
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(estimated_cost_usd), 0.0) as cost FROM engine_usage WHERE created_at >= ?",
                (month_start,),
            ).fetchone()
            return {"cost": row["cost"]}

    # ------------------------------------------------------------------
    # Budget checks
    # ------------------------------------------------------------------

    def check_user_chat_limit(self, user_id: int) -> bool:
        """True if the user can make another chat request today."""
        stats = self._sum_today("chat", user_id)
        return stats["count"] < self.config.max_chat_requests_per_day

    def check_daily_budget(self) -> bool:
        """True if today's global spend is under the daily cap."""
        stats = self._sum_today()
        return stats["cost"] < self.config.daily_budget_usd

    def check_monthly_budget(self) -> bool:
        """True if this month's global spend is under the monthly cap."""
        stats = self._sum_month()
        return stats["cost"] < self.config.monthly_budget_usd

    def check_daily_collection_limit(self) -> bool:
        """True if more collection jobs can run today."""
        stats = self._sum_today("collection")
        return stats["count"] < self.config.max_daily_collection_jobs

    def check_daily_briefing_generation_limit(self) -> bool:
        """True if more briefing generations can run today."""
        stats = self._sum_today("llm_cheap")
        expensive = self._sum_today("llm_expensive")
        total = stats["count"] + expensive["count"]
        return total < self.config.max_daily_briefing_generations

    def check_expensive_llm_limit(self) -> bool:
        """True if more expensive LLM calls can run today."""
        stats = self._sum_today("llm_expensive")
        return stats["count"] < self.config.max_daily_expensive_llm_calls

    def can_start_external_job(self) -> bool:
        """Composite check: can we start any new external work?"""
        return (
            self.check_daily_budget()
            and self.check_monthly_budget()
            and self.check_daily_collection_limit()
        )

    def get_usage_summary(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Return a summary of current usage for display."""
        daily = self._sum_today(user_id=user_id)
        monthly = self._sum_month()
        return {
            "daily_cost_usd": daily["cost"],
            "daily_tokens": daily["tokens"],
            "daily_events": daily["count"],
            "monthly_cost_usd": monthly["cost"],
            "limits": {
                "daily_budget_usd": self.config.daily_budget_usd,
                "monthly_budget_usd": self.config.monthly_budget_usd,
                "max_chat_per_day": self.config.max_chat_requests_per_day,
                "max_daily_collection": self.config.max_daily_collection_jobs,
                "max_daily_briefing_gen": self.config.max_daily_briefing_generations,
            },
        }

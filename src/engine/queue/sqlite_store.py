"""SQLite-backed job queue with atomic claim and deduplication.

Uses WAL mode and row-level locking via UPDATE ... WHERE for safe
concurrent access from a small number of workers.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.engine.models import Job, JobStatus
from src.engine.queue.store import QueueStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS engine_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type        TEXT    NOT NULL,
    dedupe_key      TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending',
    priority        INTEGER NOT NULL DEFAULT 50,
    payload_json    TEXT    NOT NULL DEFAULT '{}',
    result_json     TEXT    NOT NULL DEFAULT '{}',
    error_message   TEXT    NOT NULL DEFAULT '',
    retry_count     INTEGER NOT NULL DEFAULT 0,
    max_retries     INTEGER NOT NULL DEFAULT 3,
    lease_owner     TEXT,
    lease_expires_at TEXT,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at      TEXT,
    completed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_engine_jobs_status_priority
    ON engine_jobs (status, priority DESC);
CREATE INDEX IF NOT EXISTS idx_engine_jobs_dedupe
    ON engine_jobs (dedupe_key, status);
"""


class SQLiteQueueStore(QueueStore):
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
        conn.execute("PRAGMA foreign_keys=ON")
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

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        d = dict(row)
        d["payload_json"] = json.loads(d.get("payload_json") or "{}")
        d["result_json"] = json.loads(d.get("result_json") or "{}")
        return Job(**d)

    # ------------------------------------------------------------------
    # QueueStore interface
    # ------------------------------------------------------------------

    def enqueue(self, job: Job) -> Job:
        with self._connect() as conn:
            existing = self._find_duplicate_conn(conn, job.dedupe_key)
            if existing is not None:
                return existing
            cursor = conn.execute(
                """INSERT INTO engine_jobs
                   (job_type, dedupe_key, status, priority, payload_json,
                    max_retries, created_at)
                   VALUES (?, ?, 'pending', ?, ?, ?, CURRENT_TIMESTAMP)""",
                (
                    job.job_type,
                    job.dedupe_key,
                    job.priority,
                    json.dumps(job.payload_json, ensure_ascii=False),
                    job.max_retries,
                ),
            )
            conn.commit()
            job.id = cursor.lastrowid
            job.status = JobStatus.PENDING
            return job

    def claim(self, worker_id: str, lease_seconds: int = 300) -> Optional[Job]:
        expires = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            # Atomic claim: UPDATE with WHERE ensures only one worker wins.
            cursor = conn.execute(
                """UPDATE engine_jobs
                   SET status = 'running',
                       lease_owner = ?,
                       lease_expires_at = ?,
                       started_at = ?
                   WHERE id = (
                       SELECT id FROM engine_jobs
                       WHERE status = 'pending'
                       ORDER BY priority DESC, created_at ASC
                       LIMIT 1
                   )""",
                (worker_id, expires, now),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM engine_jobs WHERE lease_owner = ? AND status = 'running' ORDER BY started_at DESC LIMIT 1",
                (worker_id,),
            ).fetchone()
            return self._row_to_job(row) if row else None

    def complete(self, job_id: int, result: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """UPDATE engine_jobs
                   SET status = 'completed',
                       result_json = ?,
                       completed_at = ?,
                       lease_owner = NULL,
                       lease_expires_at = NULL
                   WHERE id = ?""",
                (json.dumps(result, ensure_ascii=False), now, job_id),
            )
            conn.commit()

    def fail(self, job_id: int, error: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT retry_count, max_retries FROM engine_jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return
            retry_count = row["retry_count"] + 1
            if retry_count < row["max_retries"]:
                new_status = "pending"
            else:
                new_status = "failed"
            conn.execute(
                """UPDATE engine_jobs
                   SET status = ?,
                       error_message = ?,
                       retry_count = ?,
                       lease_owner = NULL,
                       lease_expires_at = NULL,
                       completed_at = CASE WHEN ? = 'failed' THEN CURRENT_TIMESTAMP ELSE NULL END
                   WHERE id = ?""",
                (new_status, error, retry_count, new_status, job_id),
            )
            conn.commit()

    def cancel(self, job_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE engine_jobs SET status = 'cancelled', lease_owner = NULL, lease_expires_at = NULL WHERE id = ? AND status IN ('pending', 'running')",
                (job_id,),
            )
            conn.commit()

    def recover_expired_leases(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE engine_jobs
                   SET status = 'pending',
                       lease_owner = NULL,
                       lease_expires_at = NULL
                   WHERE status = 'running'
                     AND lease_expires_at IS NOT NULL
                     AND lease_expires_at < ?""",
                (now,),
            )
            conn.commit()
            return cursor.rowcount

    def get_job(self, job_id: int) -> Optional[Job]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM engine_jobs WHERE id = ?", (job_id,)).fetchone()
            return self._row_to_job(row) if row else None

    def get_pending_count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM engine_jobs WHERE status = 'pending'").fetchone()[0]

    def get_running_count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM engine_jobs WHERE status = 'running'").fetchone()[0]

    def find_duplicate(self, dedupe_key: str) -> Optional[Job]:
        with self._connect() as conn:
            return self._find_duplicate_conn(conn, dedupe_key)

    def _find_duplicate_conn(self, conn: sqlite3.Connection, dedupe_key: str) -> Optional[Job]:
        row = conn.execute(
            "SELECT * FROM engine_jobs WHERE dedupe_key = ? AND status IN ('pending', 'running') LIMIT 1",
            (dedupe_key,),
        ).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(
        self,
        *,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Job]:
        clauses = []
        params: list = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if job_type:
            clauses.append("job_type = ?")
            params.append(job_type)
        where = " AND ".join(clauses)
        sql = f"SELECT * FROM engine_jobs {('WHERE ' + where) if where else ''} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return [self._row_to_job(r) for r in conn.execute(sql, params).fetchall()]

    def purge_completed(self, older_than_hours: int = 72) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=older_than_hours)).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM engine_jobs WHERE status IN ('completed', 'failed', 'cancelled') AND completed_at < ?",
                (cutoff,),
            )
            conn.commit()
            return cursor.rowcount

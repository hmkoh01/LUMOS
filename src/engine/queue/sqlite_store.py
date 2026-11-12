"""SQLite-backed job queue with atomic claim and deduplication.

Uses WAL mode and row-level locking via UPDATE ... WHERE for safe
concurrent access from a small number of workers.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from urllib.parse import urlsplit
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
    ,available_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_engine_jobs_status_priority
    ON engine_jobs (status, priority DESC);
CREATE INDEX IF NOT EXISTS idx_engine_jobs_dedupe
    ON engine_jobs (dedupe_key, status);
CREATE TABLE IF NOT EXISTS engine_source_request_budget (
    source_id       TEXT NOT NULL,
    request_day     TEXT NOT NULL,
    request_count   INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_id, request_day)
);
CREATE TABLE IF NOT EXISTS engine_opendart_corporation_codes (
    normalized_name TEXT NOT NULL,
    corp_code       TEXT NOT NULL,
    corp_name       TEXT NOT NULL,
    stock_code      TEXT NOT NULL DEFAULT '',
    modify_date     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (normalized_name, corp_code)
);
CREATE TABLE IF NOT EXISTS engine_source_cache_state (
    cache_key       TEXT PRIMARY KEY,
    refreshed_at    TEXT NOT NULL,
    record_count    INTEGER NOT NULL,
    status          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_engine_opendart_corporation_stock
    ON engine_opendart_corporation_codes (stock_code);
CREATE TABLE IF NOT EXISTS engine_source_collection_observations (
    observation_key TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    request_count   INTEGER NOT NULL DEFAULT 0,
    provider_code   TEXT NOT NULL DEFAULT '',
    observed_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_engine_source_collection_observations_source
    ON engine_source_collection_observations (source_id, observed_at DESC);
CREATE TABLE IF NOT EXISTS source_discovery_backlog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    provider_name TEXT NOT NULL DEFAULT '',
    official_url TEXT NOT NULL,
    documentation_url TEXT NOT NULL DEFAULT '',
    registration_url TEXT NOT NULL DEFAULT '',
    categories_json TEXT NOT NULL DEFAULT '[]',
    authentication TEXT NOT NULL DEFAULT 'unknown',
    registration_required INTEGER NOT NULL DEFAULT 0,
    license_review_status TEXT NOT NULL DEFAULT 'not_reviewed',
    capabilities_json TEXT NOT NULL DEFAULT '{}',
    date_coverage TEXT NOT NULL DEFAULT 'unknown',
    demand_count INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    entry_kind TEXT NOT NULL DEFAULT 'source_candidate',
    candidate_status TEXT NOT NULL DEFAULT 'discovered',
    adapter_status TEXT NOT NULL DEFAULT 'adapter_needed',
    discovery_origin TEXT NOT NULL DEFAULT 'seed',
    next_action TEXT NOT NULL DEFAULT '',
    discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at TEXT,
    last_demand_at TEXT,
    lease_owner TEXT,
    lease_expires_at TEXT,
    UNIQUE(source_id, domain)
);
CREATE INDEX IF NOT EXISTS idx_source_discovery_status_priority
    ON source_discovery_backlog (candidate_status, priority DESC, demand_count DESC);
CREATE TABLE IF NOT EXISTS source_discovery_demand_windows (
    source_id TEXT NOT NULL,
    category TEXT NOT NULL,
    window_key TEXT NOT NULL,
    demand_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_id, category, window_key)
);
"""


class SQLiteQueueStore(QueueStore):
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or ":memory:")
        # ``:memory:`` intentionally shares one connection across test
        # threads.  SQLite connections themselves are not concurrent
        # transaction objects, so serialize only the in-process claim path;
        # file-backed stores still use their durable SQL lease transaction.
        self._claim_lock = threading.RLock()
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
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(engine_jobs)")}
        if "available_at" not in columns:
            conn.execute("ALTER TABLE engine_jobs ADD COLUMN available_at TEXT")
            conn.execute("UPDATE engine_jobs SET available_at = created_at WHERE available_at IS NULL")
        discovery_columns = {row["name"] for row in conn.execute("PRAGMA table_info(source_discovery_backlog)")}
        if discovery_columns and "next_action" not in discovery_columns:
            conn.execute("ALTER TABLE source_discovery_backlog ADD COLUMN next_action TEXT NOT NULL DEFAULT ''")
        if discovery_columns and "discovery_origin" not in discovery_columns:
            conn.execute("ALTER TABLE source_discovery_backlog ADD COLUMN discovery_origin TEXT NOT NULL DEFAULT 'seed'")
        if discovery_columns and "provider_name" not in discovery_columns:
            conn.execute("ALTER TABLE source_discovery_backlog ADD COLUMN provider_name TEXT NOT NULL DEFAULT ''")
        if discovery_columns and "entry_kind" not in discovery_columns:
            conn.execute("ALTER TABLE source_discovery_backlog ADD COLUMN entry_kind TEXT NOT NULL DEFAULT 'source_candidate'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_engine_jobs_available ON engine_jobs (status, available_at, priority DESC)")
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
                   max_retries, created_at, available_at)
                   VALUES (?, ?, 'pending', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
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

    def enqueue_once(self, job: Job) -> Job:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM engine_jobs WHERE dedupe_key = ? ORDER BY id DESC LIMIT 1",
                (job.dedupe_key,),
            ).fetchone()
            if row is not None:
                return self._row_to_job(row)
            cursor = conn.execute(
                """INSERT INTO engine_jobs
                   (job_type, dedupe_key, status, priority, payload_json,
                   max_retries, created_at, available_at)
                   VALUES (?, ?, 'pending', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                (job.job_type, job.dedupe_key, job.priority,
                 json.dumps(job.payload_json, ensure_ascii=False), job.max_retries),
            )
            conn.commit()
            job.id = cursor.lastrowid
            job.status = JobStatus.PENDING
            return job

    def claim(self, worker_id: str, lease_seconds: int = 300) -> Optional[Job]:
        expires = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        with self._claim_lock:
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
                             AND (available_at IS NULL OR available_at <= ?)
                           ORDER BY priority DESC, created_at ASC
                           LIMIT 1
                       )""",
                    (worker_id, expires, now, now),
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
                       available_at = CURRENT_TIMESTAMP,
                       completed_at = CASE WHEN ? = 'failed' THEN CURRENT_TIMESTAMP ELSE NULL END
                   WHERE id = ?""",
                (new_status, error, retry_count, new_status, job_id),
            )
            conn.commit()

    def defer(self, job_id: int, delay_seconds: float, reason: str = "") -> None:
        available_at = (datetime.now(timezone.utc) + timedelta(seconds=max(0.0, delay_seconds))).isoformat()
        with self._connect() as conn:
            conn.execute(
                """UPDATE engine_jobs
                   SET status = 'pending', error_message = ?, lease_owner = NULL,
                       lease_expires_at = NULL, available_at = ?
                   WHERE id = ? AND status = 'running'""",
                (reason, available_at, job_id),
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
                       lease_expires_at = NULL,
                       available_at = ?
                   WHERE status = 'running'
                     AND lease_expires_at IS NOT NULL
                     AND lease_expires_at < ?""",
                (now, now),
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

    def get_job_by_dedupe_key(self, dedupe_key: str) -> Optional[Job]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM engine_jobs WHERE dedupe_key = ? ORDER BY id DESC LIMIT 1",
                (dedupe_key,),
            ).fetchone()
            return self._row_to_job(row) if row else None

    def reserve_source_request(self, source_id: str, request_day: str, max_requests: int) -> bool:
        """Reserve a daily source request with one SQLite write transaction."""
        if max_requests <= 0:
            return False
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO engine_source_request_budget
                   (source_id, request_day, request_count, updated_at)
                   VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                   ON CONFLICT(source_id, request_day) DO UPDATE SET
                       request_count = request_count + 1,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE request_count < ?""",
                (source_id, request_day, max_requests),
            )
            conn.commit()
            return cursor.rowcount == 1

    def get_source_request_usage(self, source_id: str, request_day: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT request_count FROM engine_source_request_budget WHERE source_id = ? AND request_day = ?",
                (source_id, request_day),
            ).fetchone()
            return int(row["request_count"]) if row else 0

    def record_source_collection_observation(
        self, observation_key: str, source_id: str, outcome: str, *, candidate_count: int,
        request_count: int, provider_code: str = "", observed_at: Optional[str] = None,
    ) -> None:
        """Persist only non-content operational outcome metadata for a source."""
        allowed = {"normal_empty", "candidates_available", "collection_failed"}
        if outcome not in allowed:
            raise ValueError("unsupported source collection outcome")
        when = observed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO engine_source_collection_observations
                   (observation_key, source_id, outcome, candidate_count, request_count, provider_code, observed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(observation_key) DO UPDATE SET
                     outcome=excluded.outcome, candidate_count=excluded.candidate_count,
                     request_count=excluded.request_count, provider_code=excluded.provider_code,
                     observed_at=excluded.observed_at""",
                (str(observation_key), str(source_id), outcome, max(0, int(candidate_count)),
                 max(0, int(request_count)), str(provider_code or "")[:80], when),
            )
            conn.commit()

    def get_source_collection_observation(self, observation_key: str, source_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT outcome, candidate_count, request_count, provider_code, observed_at "
                "FROM engine_source_collection_observations WHERE observation_key = ? AND source_id = ?",
                (str(observation_key), str(source_id)),
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Shared source-discovery backlog (official-source metadata only)
    # ------------------------------------------------------------------

    def upsert_source_discovery_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Store only non-secret, operator-reviewable source metadata."""
        required = ("source_id", "domain", "official_url")
        if any(not str(candidate.get(field) or "").strip() for field in required):
            raise ValueError("source discovery candidate requires source_id, domain and official_url")
        statuses = {"discovered", "requires_registration", "permission_review", "adapter_needed", "ready_for_canary", "canary_passed", "approved", "enabled", "rejected"}
        status = str(candidate.get("candidate_status") or "discovered")
        if status not in statuses:
            raise ValueError("unsupported source discovery status")
        entry_kind = str(candidate.get("entry_kind") or "source_candidate")
        if entry_kind not in {"source_candidate", "discovery_infrastructure"}:
            raise ValueError("unsupported source discovery entry kind")
        for field in ("official_url", "documentation_url", "registration_url"):
            value = str(candidate.get(field) or "")
            query_keys = [part.split("=", 1)[0].casefold() for part in urlsplit(value).query.split("&") if part]
            if any(any(word in key for word in ("servicekey", "apikey", "token", "auth", "secret")) for key in query_keys):
                raise ValueError("source discovery URLs must not include credentials")
        def _contains_secret_key(value: Any) -> bool:
            if isinstance(value, dict):
                return any(any(word in str(key).casefold() for word in ("secret", "password", "authorization", "api_key", "token")) or _contains_secret_key(item) for key, item in value.items())
            if isinstance(value, (list, tuple)):
                return any(_contains_secret_key(item) for item in value)
            return False
        if _contains_secret_key(candidate.get("capabilities") or {}):
            raise ValueError("source discovery capabilities must not contain credentials")
        source_id, domain = str(candidate["source_id"]).strip().casefold(), str(candidate["domain"]).strip().casefold()
        categories = sorted({str(value).strip() for value in candidate.get("categories", []) if str(value).strip()})
        capabilities = dict(candidate.get("capabilities") or {})
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO source_discovery_backlog
                   (source_id, domain, provider_name, official_url, documentation_url, registration_url, categories_json,
                    authentication, registration_required, license_review_status, capabilities_json,
                    date_coverage, priority, entry_kind, candidate_status, adapter_status, discovery_origin, next_action, discovered_at, verified_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_id, domain) DO UPDATE SET
                     provider_name=excluded.provider_name, official_url=excluded.official_url, documentation_url=excluded.documentation_url,
                     registration_url=excluded.registration_url, categories_json=excluded.categories_json,
                     authentication=excluded.authentication, registration_required=excluded.registration_required,
                     license_review_status=excluded.license_review_status, capabilities_json=excluded.capabilities_json,
                     date_coverage=excluded.date_coverage, priority=MAX(source_discovery_backlog.priority, excluded.priority),
                     entry_kind=excluded.entry_kind,
                     adapter_status=excluded.adapter_status, discovery_origin=excluded.discovery_origin,
                     next_action=excluded.next_action, verified_at=excluded.verified_at""",
                (source_id, domain, str(candidate.get("provider_name") or ""), str(candidate["official_url"]),
                 str(candidate.get("documentation_url") or ""), str(candidate.get("registration_url") or ""), json.dumps(categories, ensure_ascii=False),
                 str(candidate.get("authentication") or "unknown"), int(bool(candidate.get("registration_required"))),
                 str(candidate.get("license_review_status") or "not_reviewed"), json.dumps(capabilities, ensure_ascii=False),
                 str(candidate.get("date_coverage") or "unknown"), max(0, int(candidate.get("priority") or 0)), entry_kind, status,
                 str(candidate.get("adapter_status") or "adapter_needed"), str(candidate.get("discovery_origin") or "manual")[:64],
                 str(candidate.get("next_action") or "")[:500], now, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM source_discovery_backlog WHERE source_id=? AND domain=?", (source_id, domain)).fetchone()
        return self._source_discovery_row(row)

    def record_source_discovery_demand(self, source_id: str, category: str, window_key: str, *, user_count: int) -> bool:
        """Record one scheduler-aggregated demand window; never persist user IDs."""
        if user_count <= 0:
            return False
        source_id = str(source_id).casefold()
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO source_discovery_demand_windows (source_id, category, window_key, demand_count)
                   VALUES (?, ?, ?, ?) ON CONFLICT(source_id, category, window_key) DO NOTHING""",
                (source_id, str(category), str(window_key), int(user_count)),
            )
            if cursor.rowcount:
                conn.execute("UPDATE source_discovery_backlog SET demand_count=demand_count+?, last_demand_at=CURRENT_TIMESTAMP WHERE source_id=?", (int(user_count), source_id))
            conn.commit()
            return cursor.rowcount == 1

    def record_source_discovery_subject_demand(self, source_id: str, category: str, window_key: str, *, subject_digest: str) -> bool:
        """Deduplicate one opaque, window-scoped subject token without storing a user ID."""
        token = str(subject_digest or "").strip()
        if len(token) < 16:
            raise ValueError("source discovery subject token is invalid")
        source_id = str(source_id).casefold()
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS source_discovery_demand_subjects (
                   source_id TEXT NOT NULL, category TEXT NOT NULL, window_key TEXT NOT NULL,
                   subject_digest TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                   PRIMARY KEY (source_id, category, window_key, subject_digest))"""
            )
            cursor = conn.execute(
                """INSERT INTO source_discovery_demand_subjects (source_id, category, window_key, subject_digest)
                   VALUES (?, ?, ?, ?) ON CONFLICT(source_id, category, window_key, subject_digest) DO NOTHING""",
                (source_id, str(category), str(window_key), token),
            )
            if cursor.rowcount:
                conn.execute("UPDATE source_discovery_backlog SET demand_count=demand_count+1, last_demand_at=CURRENT_TIMESTAMP WHERE source_id=?", (source_id,))
            conn.commit()
            return cursor.rowcount == 1

    def claim_source_discovery_candidate(self, source_id: str, worker_id: str, *, lease_seconds: int = 300) -> bool:
        expires = (datetime.now(timezone.utc) + timedelta(seconds=max(1, lease_seconds))).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE source_discovery_backlog SET lease_owner=?, lease_expires_at=?
                   WHERE source_id=? AND candidate_status='discovered' AND (lease_expires_at IS NULL OR lease_expires_at < ?)""",
                (str(worker_id), expires, str(source_id).casefold(), now),
            )
            conn.commit()
            return cursor.rowcount == 1

    def list_source_discovery_backlog(self, *, limit: int = 100, registration_required: Optional[bool] = None,
                                      permission_review: bool = False, adapter_needed: bool = False,
                                      entry_kind: Optional[str] = None) -> List[Dict[str, Any]]:
        clauses, params = [], []
        if registration_required is not None:
            clauses.append("registration_required=?")
            params.append(int(registration_required))
        if permission_review:
            clauses.append("(candidate_status='permission_review' OR license_review_status LIKE '%review%')")
        if adapter_needed:
            # ``schema_pending`` is a stricter form of adapter work: its
            # connector may exist, but a provider-issued schema is still
            # required before any network call can be made.
            clauses.append("adapter_status IN ('adapter_needed', 'schema_pending')")
        if entry_kind is not None:
            if entry_kind not in {"source_candidate", "discovery_infrastructure"}:
                raise ValueError("unsupported source discovery entry kind")
            clauses.append("entry_kind=?")
            params.append(entry_kind)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM source_discovery_backlog {where} ORDER BY demand_count DESC, priority DESC, id ASC LIMIT ?", [*params, max(1, min(int(limit), 500))]).fetchall()
        return [self._source_discovery_row(row) for row in rows]

    @staticmethod
    def _source_discovery_row(row: sqlite3.Row) -> Dict[str, Any]:
        result = dict(row)
        result["categories"] = json.loads(result.pop("categories_json") or "[]")
        result["capabilities"] = json.loads(result.pop("capabilities_json") or "{}")
        result["registration_required"] = bool(result.get("registration_required"))
        return result

    # ------------------------------------------------------------------
    # Shared source metadata caches (no raw provider archives)
    # ------------------------------------------------------------------

    def replace_opendart_corporation_directory(self, records: List[Dict[str, str]], *, refreshed_at: Optional[str] = None) -> int:
        """Atomically replace a verified directory after a successful refresh.

        A failed download never invokes this method, preserving the last known
        good cache for every Worker sharing this queue database.
        """
        cleaned = [
            (
                str(record["normalized_name"]), str(record["corp_code"]), str(record["corp_name"]),
                str(record.get("stock_code") or ""), str(record.get("modify_date") or ""),
            )
            for record in records
            if record.get("normalized_name") and record.get("corp_code") and record.get("corp_name")
        ]
        if not cleaned:
            raise ValueError("refusing to replace corporation directory with no verified records")
        refreshed = refreshed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM engine_opendart_corporation_codes")
            conn.executemany(
                """INSERT INTO engine_opendart_corporation_codes
                   (normalized_name, corp_code, corp_name, stock_code, modify_date)
                   VALUES (?, ?, ?, ?, ?)""",
                cleaned,
            )
            conn.execute(
                """INSERT INTO engine_source_cache_state (cache_key, refreshed_at, record_count, status)
                   VALUES ('opendart_corporation_directory', ?, ?, 'ready')
                   ON CONFLICT(cache_key) DO UPDATE SET refreshed_at=excluded.refreshed_at,
                   record_count=excluded.record_count, status=excluded.status""",
                (refreshed, len(cleaned)),
            )
            conn.commit()
        return len(cleaned)

    def resolve_opendart_corporation(self, normalized_name: str, *, max_age_seconds: int) -> Dict[str, Any]:
        """Resolve an exact corporate name from the durable shared directory."""
        with self._connect() as conn:
            state = conn.execute(
                "SELECT refreshed_at, record_count, status FROM engine_source_cache_state WHERE cache_key = 'opendart_corporation_directory'"
            ).fetchone()
            if not state or state["status"] != "ready":
                return {"state": "cache_unavailable"}
            try:
                refreshed = datetime.fromisoformat(str(state["refreshed_at"]).replace("Z", "+00:00"))
                if refreshed.tzinfo is None:
                    refreshed = refreshed.replace(tzinfo=timezone.utc)
            except ValueError:
                return {"state": "cache_unavailable"}
            if (datetime.now(timezone.utc) - refreshed.astimezone(timezone.utc)).total_seconds() > max(0, max_age_seconds):
                return {"state": "cache_stale", "refreshed_at": state["refreshed_at"]}
            rows = conn.execute(
                """SELECT corp_code, corp_name, stock_code, modify_date
                   FROM engine_opendart_corporation_codes WHERE normalized_name = ?""",
                (normalized_name,),
            ).fetchall()
        if not rows:
            return {"state": "not_found"}
        if len(rows) != 1:
            return {"state": "ambiguous"}
        return {"state": "resolved", **dict(rows[0]), "refreshed_at": state["refreshed_at"]}

    def resolve_opendart_corporation_by_stock_code(self, stock_code: str, *, max_age_seconds: int) -> Dict[str, Any]:
        """Resolve only an exact, unique official stock code from the shared cache."""
        code = str(stock_code or "").strip()
        if not code or not code.isdigit():
            return {"state": "not_found"}
        with self._connect() as conn:
            state = conn.execute(
                "SELECT refreshed_at, record_count, status FROM engine_source_cache_state WHERE cache_key = 'opendart_corporation_directory'"
            ).fetchone()
            if not state or state["status"] != "ready":
                return {"state": "cache_unavailable"}
            try:
                refreshed = datetime.fromisoformat(str(state["refreshed_at"]).replace("Z", "+00:00"))
                if refreshed.tzinfo is None:
                    refreshed = refreshed.replace(tzinfo=timezone.utc)
            except ValueError:
                return {"state": "cache_unavailable"}
            if (datetime.now(timezone.utc) - refreshed.astimezone(timezone.utc)).total_seconds() > max(0, max_age_seconds):
                return {"state": "cache_stale", "refreshed_at": state["refreshed_at"]}
            rows = conn.execute(
                "SELECT corp_code, corp_name, stock_code, modify_date FROM engine_opendart_corporation_codes WHERE stock_code = ?",
                (code,),
            ).fetchall()
        if not rows:
            return {"state": "not_found"}
        if len(rows) != 1:
            return {"state": "ambiguous"}
        return {"state": "resolved", **dict(rows[0]), "refreshed_at": state["refreshed_at"]}

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

    def monitoring_summary(self) -> Dict[str, Any]:
        """Return aggregate queue health without job payloads or error contents."""
        with self._connect() as conn:
            status_rows = conn.execute(
                "SELECT job_type, status, COUNT(*) AS count FROM engine_jobs GROUP BY job_type, status"
            ).fetchall()
            wait_row = conn.execute(
                """SELECT AVG((julianday(started_at) - julianday(created_at)) * 86400.0) AS avg_wait
                   FROM engine_jobs WHERE started_at IS NOT NULL"""
            ).fetchone()
            executions = conn.execute(
                "SELECT COUNT(*) FROM engine_jobs WHERE status IN ('running', 'completed', 'failed')"
            ).fetchone()[0]
        return {
            "jobs": {f"{row['job_type']}:{row['status']}": row["count"] for row in status_rows},
            "average_wait_seconds": float(wait_row["avg_wait"] or 0.0),
            "execution_count": int(executions),
        }

    def close(self) -> None:
        """Release the in-memory connection; file-backed operations are per-call."""
        if self._shared_conn is not None:
            self._shared_conn.close()
            self._shared_conn = None

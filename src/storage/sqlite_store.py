import json
import hashlib
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.app.config import get_database_path
from src.storage.migrations import MIGRATION_COLUMNS, SCHEMA_STATEMENTS
from src.storage.schemas import DEFAULT_CONNECTORS, DEFAULT_SOURCE_CONFIGS, DEFAULT_SOURCES


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


class SQLiteStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or get_database_path())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self):
        with self.connect() as conn:
            deferred_statements = []
            for statement in SCHEMA_STATEMENTS:
                try:
                    conn.execute(statement)
                except sqlite3.OperationalError as exc:
                    if "no such column" in str(exc).lower() and "index" in statement.lower():
                        deferred_statements.append(statement)
                    else:
                        raise
            self._apply_column_migrations(conn)
            for statement in deferred_statements:
                conn.execute(statement)
            self._ensure_defaults(conn)
            conn.commit()

    def _apply_column_migrations(self, conn: sqlite3.Connection):
        for table, columns in MIGRATION_COLUMNS.items():
            existing = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for column, definition in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _ensure_defaults(self, conn: sqlite3.Connection):
        conn.execute(
            """
            INSERT OR IGNORE INTO user_settings
            (id, signal_count, briefing_time, timezone, enabled_sources_json,
             enabled_connectors_json, desktop_push_enabled, generate_mode, sync_before_briefing,
             context_sync_interval_minutes, max_interest_keywords, mode_enabled, onboarding_completed)
            VALUES (1, 3, '08:00', 'Asia/Seoul', ?, ?, 1, 'mock', 1, 360, 50, 1, 0)
            """,
            (self.dumps(DEFAULT_SOURCES), self.dumps(DEFAULT_CONNECTORS)),
        )
        for connector_type, enabled in DEFAULT_CONNECTORS.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO connectors
                (connector_type, enabled, auth_status, config_json)
                VALUES (?, ?, 'not_connected', '{}')
                """,
                (connector_type, 1 if enabled else 0),
            )
        self._seed_default_source_configs(conn, overwrite=False)

    def _seed_default_source_configs(self, conn: sqlite3.Connection, overwrite: bool = False):
        for source_id, config in DEFAULT_SOURCE_CONFIGS.items():
            if overwrite:
                conn.execute(
                    """
                    INSERT INTO source_configs
                    (source_id, enabled, display_name, config_json, priority, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(source_id) DO UPDATE SET
                        enabled = excluded.enabled,
                        display_name = excluded.display_name,
                        config_json = excluded.config_json,
                        priority = excluded.priority,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        source_id,
                        1 if config.get("enabled") else 0,
                        config.get("display_name", source_id),
                        self.dumps(config.get("config_json", {})),
                        int(config.get("priority", 50)),
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO source_configs
                    (source_id, enabled, display_name, config_json, priority)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        1 if config.get("enabled") else 0,
                        config.get("display_name", source_id),
                        self.dumps(config.get("config_json", {})),
                        int(config.get("priority", 50)),
                    ),
                )

    def dumps(self, value: Any) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False)

    def loads(self, value: Any, default: Any):
        if value is None or value == "":
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return default

    def get_settings(self) -> Dict[str, Any]:
        with self.connect() as conn:
            self._ensure_defaults(conn)
            row = conn.execute("SELECT * FROM user_settings WHERE id = 1").fetchone()
            result = dict(row)
            result["enabled_sources_json"] = self.loads(result["enabled_sources_json"], DEFAULT_SOURCES)
            result["enabled_connectors_json"] = self.loads(result["enabled_connectors_json"], DEFAULT_CONNECTORS)
            result["desktop_push_enabled"] = bool(result["desktop_push_enabled"])
            result["sync_before_briefing"] = bool(result.get("sync_before_briefing", 1))
            result["auto_expand_interests"] = bool(result.get("auto_expand_interests", 0))
            result["mode_enabled"] = bool(result["mode_enabled"])
            result["onboarding_completed"] = bool(result["onboarding_completed"])
            return result

    def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {
            "signal_count",
            "briefing_time",
            "timezone",
            "enabled_sources_json",
            "enabled_connectors_json",
            "desktop_push_enabled",
            "generate_mode",
            "sync_before_briefing",
            "auto_expand_interests",
            "context_sync_interval_minutes",
            "max_interest_keywords",
            "mode_enabled",
            "onboarding_completed",
        }
        assignments = []
        params = []
        for key, value in updates.items():
            if key not in allowed or value is None:
                continue
            if key == "signal_count":
                value = max(1, int(value))
            elif key == "context_sync_interval_minutes":
                value = max(1, int(value))
            elif key == "max_interest_keywords":
                value = max(1, int(value))
            elif key == "generate_mode":
                value = value if value in {"mock", "hybrid", "live"} else "mock"
            elif key in {"enabled_sources_json", "enabled_connectors_json"}:
                value = self.dumps(value)
            elif key in {"desktop_push_enabled", "sync_before_briefing", "auto_expand_interests", "mode_enabled", "onboarding_completed"}:
                value = 1 if bool(value) else 0
            assignments.append(f"{key} = ?")
            params.append(value)

        if assignments:
            assignments.append("updated_at = CURRENT_TIMESTAMP")
            params.append(1)
            with self.connect() as conn:
                self._ensure_defaults(conn)
                conn.execute(f"UPDATE user_settings SET {', '.join(assignments)} WHERE id = ?", params)
                conn.commit()
        return self.get_settings()

    def seed_default_source_configs(self, overwrite: bool = False) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            self._seed_default_source_configs(conn, overwrite=overwrite)
            conn.commit()
        return self.get_source_configs()

    def get_source_configs(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            self._seed_default_source_configs(conn, overwrite=False)
            rows = conn.execute(
                """
                SELECT * FROM source_configs
                ORDER BY enabled DESC, priority DESC, source_id ASC
                """
            ).fetchall()
            return [self._source_config_from_row(row) for row in rows]

    def get_source_config(self, source_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            self._seed_default_source_configs(conn, overwrite=False)
            row = conn.execute("SELECT * FROM source_configs WHERE source_id = ?", (source_id,)).fetchone()
            return self._source_config_from_row(row) if row else None

    def get_enabled_source_configs(self) -> List[Dict[str, Any]]:
        return [config for config in self.get_source_configs() if config["enabled"]]

    def upsert_source_config(
        self,
        source_id: str,
        enabled: Optional[bool] = None,
        priority: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = self.get_source_config(source_id) or {
            "source_id": source_id,
            "enabled": False,
            "display_name": display_name or source_id,
            "priority": 50,
            "config_json": {},
        }
        next_enabled = existing["enabled"] if enabled is None else bool(enabled)
        next_priority = existing["priority"] if priority is None else int(priority)
        next_config = existing["config_json"] if config is None else config
        next_display_name = display_name or existing.get("display_name") or source_id
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_configs
                (source_id, enabled, display_name, config_json, priority, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    display_name = excluded.display_name,
                    config_json = excluded.config_json,
                    priority = excluded.priority,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    source_id,
                    1 if next_enabled else 0,
                    next_display_name,
                    self.dumps(next_config),
                    next_priority,
                ),
            )
            conn.commit()
        return self.get_source_config(source_id) or {}

    def _source_config_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        item["config_json"] = self.loads(item["config_json"], {})
        return item

    def get_profile(self) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
            if not row:
                return None
            result = dict(row)
            result["goals_json"] = self.loads(result["goals_json"], [])
            result["interest_types_json"] = self.loads(result["interest_types_json"], [])
            result["raw_onboarding_json"] = self.loads(result["raw_onboarding_json"], {})
            return result

    def upsert_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_profile
                (id, role, role_detail, goals_json, interest_types_json, raw_onboarding_json, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    role = excluded.role,
                    role_detail = excluded.role_detail,
                    goals_json = excluded.goals_json,
                    interest_types_json = excluded.interest_types_json,
                    raw_onboarding_json = excluded.raw_onboarding_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    profile.get("role", ""),
                    profile.get("role_detail", ""),
                    self.dumps(profile.get("goals", [])),
                    self.dumps(profile.get("interest_types", [])),
                    self.dumps(profile.get("raw_onboarding", {})),
                ),
            )
            conn.commit()
        return self.get_profile() or {}

    def get_connectors(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            self._ensure_defaults(conn)
            rows = conn.execute("SELECT * FROM connectors ORDER BY connector_type ASC").fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["enabled"] = bool(item["enabled"])
                item["config_json"] = self.loads(item["config_json"], {})
                result.append(item)
            return result

    def update_connector(self, connector_type: str, enabled: bool, config: Optional[Dict[str, Any]] = None):
        if connector_type not in DEFAULT_CONNECTORS:
            raise ValueError(f"Unsupported connector_type: {connector_type}")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO connectors (connector_type, enabled, config_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(connector_type) DO UPDATE SET
                    enabled = excluded.enabled,
                    config_json = excluded.config_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (connector_type, 1 if enabled else 0, self.dumps(config or {})),
            )
            conn.commit()

        settings = self.get_settings()
        connector_map = settings["enabled_connectors_json"]
        connector_map[connector_type] = enabled
        self.update_settings({"enabled_connectors_json": connector_map})
        return next(item for item in self.get_connectors() if item["connector_type"] == connector_type)

    def update_connector_sync_status(
        self,
        connector_type: str,
        status: str,
        error: Optional[str] = None,
    ):
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE connectors
                SET last_sync_at = CURRENT_TIMESTAMP,
                    last_status = ?,
                    last_error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE connector_type = ?
                """,
                (status, error, connector_type),
            )
            conn.commit()

    def upsert_interest(self, keyword: str, category: Optional[str], weight: float, source: str, evidence: Dict[str, Any]):
        keyword = keyword.strip()
        if not keyword:
            return
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO interest_graph
                (keyword, category, weight, source, evidence_json, status, last_seen_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(keyword, category, source) DO UPDATE SET
                    weight = MAX(interest_graph.weight, excluded.weight),
                    evidence_json = excluded.evidence_json,
                    last_seen_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (keyword, category, float(weight), source, self.dumps(evidence)),
            )
            conn.commit()

    def adjust_interest_weight(
        self,
        keyword: str,
        delta: float,
        category: Optional[str] = None,
        source: str = "feedback",
        evidence: Optional[Dict[str, Any]] = None,
        minimum: float = 0.0,
        maximum: float = 10.0,
        reactivate: bool = False,
    ):
        keyword = keyword.strip()
        if not keyword:
            return
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM interest_graph
                WHERE keyword = ? AND COALESCE(category, '') = COALESCE(?, '') AND source = ?
                """,
                (keyword, category, source),
            ).fetchone()
            if row:
                if row["status"] in {"muted", "deleted"} and not reactivate:
                    return
                next_weight = max(minimum, min(maximum, float(row["weight"]) + float(delta)))
                conn.execute(
                    """
                    UPDATE interest_graph
                    SET weight = ?,
                        evidence_json = ?,
                        status = ?,
                        last_seen_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (next_weight, self.dumps(evidence or {}), "active" if reactivate else row["status"], row["id"]),
                )
            else:
                next_weight = max(minimum, min(maximum, max(0.1, float(delta))))
                conn.execute(
                    """
                    INSERT INTO interest_graph
                    (keyword, category, weight, source, evidence_json, status, last_seen_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (keyword, category, next_weight, source, self.dumps(evidence or {})),
                )
            conn.commit()

    def update_interest(self, keyword: str, updates: Dict[str, Any] = None, **kwargs) -> Optional[Dict[str, Any]]:
        updates = {**(updates or {}), **{key: value for key, value in kwargs.items() if value is not None}}
        with self.connect() as conn:
            assignments = []
            params: List[Any] = []
            if "weight" in updates and updates["weight"] is not None:
                assignments.append("weight = ?")
                params.append(max(0.0, float(updates["weight"])))
            if "category" in updates:
                assignments.append("category = ?")
                params.append(updates["category"])
            if "status" in updates and updates["status"] in {"active", "muted", "deleted"}:
                assignments.append("status = ?")
                params.append(updates["status"])
            if not assignments:
                return None
            assignments.append("updated_at = CURRENT_TIMESTAMP")
            params.append(keyword)
            conn.execute(f"UPDATE interest_graph SET {', '.join(assignments)} WHERE keyword = ?", params)
            conn.commit()
        matches = [item for item in self.get_interests(limit=500, include_muted=True) if item["keyword"] == keyword]
        return matches[0] if matches else None

    def add_manual_interest(self, keyword: str) -> Dict[str, Any]:
        keyword = " ".join(keyword.split())
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id FROM interest_graph WHERE keyword = ? COLLATE NOCASE ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, id LIMIT 1",
                (keyword,),
            ).fetchone()
            if row:
                interest_id = row["id"]
                conn.execute("UPDATE interest_graph SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (interest_id,))
            else:
                cursor = conn.execute(
                    "INSERT INTO interest_graph (keyword, category, weight, source, evidence_json, status, last_seen_at, updated_at) VALUES (?, 'manual', 1, 'manual', ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (keyword, self.dumps({"added_by": "user"})),
                )
                interest_id = cursor.lastrowid
            conn.execute("UPDATE user_settings SET onboarding_completed = 1 WHERE id = 1")
            result = dict(conn.execute("SELECT * FROM interest_graph WHERE id = ?", (interest_id,)).fetchone())
            result["evidence_json"] = self.loads(result["evidence_json"], {})
            conn.commit()
            return result

    def delete_interest(self, keyword: str) -> int:
        return 1 if self.update_interest(keyword, status="deleted") else 0

    def hard_delete_interest(self, keyword: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM interest_graph WHERE keyword = ?", (keyword,))
            conn.commit()
            return int(cursor.rowcount)

    def mute_interest(self, keyword: str) -> Optional[Dict[str, Any]]:
        return self.update_interest(keyword, status="muted")

    def unmute_interest(self, keyword: str) -> Optional[Dict[str, Any]]:
        return self.update_interest(keyword, status="active")

    def is_interest_blocked(self, keyword: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT status FROM interest_graph
                WHERE keyword = ? AND status IN ('muted', 'deleted')
                LIMIT 1
                """,
                (keyword,),
            ).fetchone()
            return bool(row)

    def get_interests(
        self,
        status: Optional[str] = None,
        limit: Optional[int] = 50,
        include_muted: bool = False,
        include_deleted: bool = True,
    ) -> List[Dict[str, Any]]:
        clauses = []
        params: List[Any] = []
        if not include_deleted:
            clauses.append("status != 'deleted'")
        if status:
            clauses.append("status = ?")
            params.append(status)
        elif not include_muted:
            clauses.append("status = 'active'")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_clause = "LIMIT ?" if limit is not None else ""
        if limit is not None:
            params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM interest_graph
                {where}
                ORDER BY weight DESC, last_seen_at DESC
                {limit_clause}
                """,
                params,
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["evidence_json"] = self.loads(item["evidence_json"], {})
                result.append(item)
            return result

    def get_top_interests(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.get_interests(status="active", limit=limit)

    def get_interest_evidence(self, keyword: str) -> List[Dict[str, Any]]:
        return [item for item in self.get_interests(limit=None, include_muted=True) if item["keyword"] == keyword]

    def prune_interests(self, max_keywords: int) -> Dict[str, Any]:
        active = self.get_interests(status="active", limit=None)
        if len(active) <= max_keywords:
            return {"muted": [], "kept": len(active)}
        overflow = active[max_keywords:]
        # Prefer muting low-weight personal context interests first.
        overflow = sorted(
            overflow,
            key=lambda item: (item.get("source") not in {"browser_history", "local_files"}, item.get("weight", 0), item.get("updated_at", "")),
        )
        muted = []
        for item in overflow[: len(active) - max_keywords]:
            self.mute_interest(item["keyword"])
            muted.append(item["keyword"])
        return {"muted": muted, "kept": max_keywords}

    def get_sync_settings(self) -> Dict[str, Any]:
        settings = self.get_settings()
        return {
            "sync_before_briefing": settings.get("sync_before_briefing", True),
            "context_sync_interval_minutes": int(settings.get("context_sync_interval_minutes", 360)),
            "max_interest_keywords": int(settings.get("max_interest_keywords", 50)),
        }

    def update_sync_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {"sync_before_briefing", "context_sync_interval_minutes", "max_interest_keywords"}
        return self.update_settings({key: value for key, value in updates.items() if key in allowed})

    def create_context_sync_run(self, connector_type: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO context_sync_runs (connector_type, status) VALUES (?, 'running')",
                (connector_type,),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def complete_context_sync_run(self, run_id: int, item_count: int, keyword_count: int, summary: Dict[str, Any]):
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE context_sync_runs
                SET status = 'completed',
                    completed_at = CURRENT_TIMESTAMP,
                    item_count = ?,
                    keyword_count = ?,
                    summary_json = ?
                WHERE id = ?
                """,
                (int(item_count), int(keyword_count), self.dumps(summary), run_id),
            )
            conn.commit()

    def fail_context_sync_run(self, run_id: int, error_message: str, summary: Optional[Dict[str, Any]] = None):
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE context_sync_runs
                SET status = 'failed',
                    completed_at = CURRENT_TIMESTAMP,
                    summary_json = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (self.dumps(summary or {}), error_message, run_id),
            )
            conn.commit()

    def get_recent_context_sync_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM context_sync_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["summary_json"] = self.loads(item["summary_json"], {})
                result.append(item)
            return result

    def build_context_item_dedupe_key(self, item: Dict[str, Any]) -> str:
        connector_type = self._normalize_text(item.get("connector_type", ""))
        item_id = self._normalize_text(item.get("item_id", ""))
        if item_id:
            raw = f"{connector_type}:id:{item_id}"
        elif item.get("url"):
            raw = f"{connector_type}:url:{self._normalize_text(item.get('url', ''))}"
        elif item.get("path"):
            raw = f"{connector_type}:path:{self._normalize_text(item.get('path', ''))}"
        else:
            raw = f"{connector_type}:title:{self._normalize_text(item.get('title', ''))}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def upsert_context_item(self, item: Dict[str, Any]) -> int:
        dedupe_key = item.get("dedupe_key") or self.build_context_item_dedupe_key(item)
        snippet = str(item.get("text_snippet") or item.get("text") or "")[:1000]
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO context_items
                (connector_type, item_id, dedupe_key, title, text_snippet, url, path, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dedupe_key) DO UPDATE SET
                    title = excluded.title,
                    text_snippet = excluded.text_snippet,
                    url = excluded.url,
                    path = excluded.path,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at,
                    collected_at = CURRENT_TIMESTAMP
                """,
                (
                    item["connector_type"],
                    item.get("item_id", ""),
                    dedupe_key,
                    item.get("title", ""),
                    snippet,
                    item.get("url"),
                    item.get("path"),
                    self.dumps(item.get("metadata_json", {})),
                    item.get("created_at"),
                    item.get("updated_at"),
                ),
            )
            conn.commit()
            row = conn.execute("SELECT id FROM context_items WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
            return int(row["id"]) if row else int(cursor.lastrowid or -1)

    def get_context_items(self, connector_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        query = "SELECT * FROM context_items"
        params: List[Any] = []
        if connector_type:
            query += " WHERE connector_type = ?"
            params.append(connector_type)
        query += " ORDER BY collected_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["metadata_json"] = self.loads(item["metadata_json"], {})
                result.append(item)
            return result

    def create_pipeline_run(
        self,
        run_type: str,
        triggered_by: str = "manual",
        settings_snapshot: Optional[Dict[str, Any]] = None,
        profile_snapshot: Optional[Dict[str, Any]] = None,
        interest_snapshot: Optional[List[Dict[str, Any]]] = None,
        selected_sources: Optional[List[str]] = None,
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO pipeline_runs
                (run_type, status, triggered_by, settings_snapshot_json,
                 profile_snapshot_json, interest_snapshot_json, selected_sources_json)
                VALUES (?, 'running', ?, ?, ?, ?, ?)
                """,
                (
                    run_type,
                    triggered_by,
                    self.dumps(settings_snapshot or {}),
                    self.dumps(profile_snapshot or {}),
                    self.dumps(interest_snapshot or []),
                    self.dumps(selected_sources or []),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def complete_pipeline_run(self, run_id: int, summary: Dict[str, Any]):
        with self.connect() as conn:
            selected_sources = summary.get("selected_sources")
            if selected_sources is not None:
                conn.execute(
                    """
                    UPDATE pipeline_runs
                    SET status = 'completed',
                        completed_at = CURRENT_TIMESTAMP,
                        summary_json = ?,
                        selected_sources_json = ?
                    WHERE id = ?
                    """,
                    (self.dumps(summary), self.dumps(selected_sources), run_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE pipeline_runs
                    SET status = 'completed',
                        completed_at = CURRENT_TIMESTAMP,
                        summary_json = ?
                    WHERE id = ?
                    """,
                    (self.dumps(summary), run_id),
                )
            conn.commit()

    def fail_pipeline_run(self, run_id: int, error_message: str):
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE pipeline_runs
                SET status = 'failed',
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = ?
                WHERE id = ?
                """,
                (error_message, run_id),
            )
            conn.commit()

    def get_pipeline_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                return None
            run = self._pipeline_run_from_row(row)
            run.update(self._pipeline_run_counts(conn, run_id))
            return run

    def get_recent_pipeline_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            runs = []
            for row in rows:
                run = self._pipeline_run_from_row(row)
                run.update(self._pipeline_run_counts(conn, run["id"]))
                runs.append(run)
            return runs

    def get_last_scheduled_briefing_run(self, run_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        run_date = run_date or date.today().isoformat()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM pipeline_runs
                WHERE run_type = 'scheduled_daily_briefing'
                  AND DATE(started_at) = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (run_date,),
            ).fetchone()
            if not row:
                return None
            run = self._pipeline_run_from_row(row)
            run.update(self._pipeline_run_counts(conn, run["id"]))
            return run

    def has_completed_scheduled_briefing(self, run_date: Optional[str] = None) -> bool:
        run = self.get_last_scheduled_briefing_run(run_date)
        return bool(run and run.get("status") == "completed")

    def _pipeline_run_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        run = dict(row)
        run["settings_snapshot_json"] = self.loads(run.get("settings_snapshot_json"), {})
        run["profile_snapshot_json"] = self.loads(run.get("profile_snapshot_json"), {})
        run["interest_snapshot_json"] = self.loads(run.get("interest_snapshot_json"), [])
        run["selected_sources_json"] = self.loads(run.get("selected_sources_json"), [])
        run["summary_json"] = self.loads(run.get("summary_json"), {})
        return run

    def _pipeline_run_counts(self, conn: sqlite3.Connection, run_id: int) -> Dict[str, int]:
        def count(table: str) -> int:
            return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE pipeline_run_id = ?", (run_id,)).fetchone()[0]

        return {
            "route_count": count("source_routes"),
            "source_item_count": count("source_items"),
            "candidate_count": count("signal_candidates"),
            "signal_count": count("signals"),
        }

    def build_source_item_dedupe_key(self, item: Dict[str, Any]) -> str:
        source = str(item.get("source") or "").strip().lower()
        source_item_id = str(item.get("source_item_id") or "").strip().lower()
        if source_item_id:
            raw = f"{source}:id:{source_item_id}"
        elif item.get("url"):
            raw = f"{source}:url:{self._normalize_text(item['url'])}"
        else:
            published_date = str(item.get("published_at") or "")[:10]
            raw = f"{source}:title:{self._normalize_text(item.get('title', ''))}:{published_date}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def build_candidate_dedupe_key(
        self,
        source_item_id: int,
        route_id: int,
        category: str = "",
        matched_keywords: Optional[List[str]] = None,
    ) -> str:
        matched = ",".join(sorted(matched_keywords or []))
        if matched or category:
            raw = f"item:{source_item_id}:category:{category}:matched:{matched}"
        else:
            raw = f"item:{source_item_id}:route:{route_id}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def build_signal_dedupe_key(self, signal: Dict[str, Any]) -> str:
        source_items = signal.get("source_items_json") or []
        primary = source_items[0] if source_items else {}
        primary_item_id = primary.get("source_item_id") or primary.get("id")
        if primary_item_id:
            raw = f"source_item:{primary_item_id}"
        else:
            raw = f"title:{self._normalize_text(signal.get('title', ''))}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _normalize_text(self, value: str) -> str:
        return " ".join(str(value or "").strip().lower().split())

    def create_signal(self, signal: Dict[str, Any], pipeline_run_id: Optional[int] = None) -> int:
        signal_date = signal.get("signal_date") or date.today().isoformat()
        dedupe_key = signal.get("dedupe_key") or self.build_signal_dedupe_key(signal)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO signals
                (pipeline_run_id, dedupe_key, signal_date, title, summary, why_it_matters, category, recommended_action,
                 source_name, source_url, source_items_json, metadata_json, confidence, rank, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pipeline_run_id if pipeline_run_id is not None else signal.get("pipeline_run_id"),
                    dedupe_key,
                    signal_date,
                    signal["title"],
                    signal["summary"],
                    signal["why_it_matters"],
                    signal.get("category", ""),
                    signal.get("recommended_action", ""),
                    signal.get("source_name", "Mock Source"),
                    signal.get("source_url", ""),
                    self.dumps(signal.get("source_items_json", [])),
                    self.dumps(signal.get("metadata_json", {})),
                    float(signal.get("confidence", 0.0)),
                    int(signal.get("rank", 1)),
                    signal.get("status", "new"),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def create_source_route(self, route: Dict[str, Any], pipeline_run_id: Optional[int] = None) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO source_routes
                (pipeline_run_id, route_date, source, query, limit_count, reason, category, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pipeline_run_id if pipeline_run_id is not None else route.get("pipeline_run_id"),
                    route["route_date"],
                    route["source"],
                    route["query"],
                    int(route.get("limit_count", route.get("collection_limit", 10))),
                    route.get("reason", ""),
                    route.get("category", ""),
                    route.get("status", "planned"),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_today_source_routes(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM source_routes
                WHERE route_date = ?
                ORDER BY created_at DESC
                """,
                (date.today().isoformat(),),
            ).fetchall()
            return [dict(row) for row in rows]

    def find_existing_source_item(self, source: str, source_item_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM source_items WHERE source = ? AND source_item_id = ?",
                (source, source_item_id),
            ).fetchone()
            return self._source_item_from_row(row) if row else None

    def find_existing_source_item_by_dedupe_key(self, dedupe_key: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM source_items WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
            return self._source_item_from_row(row) if row else None

    def create_source_item(self, item: Dict[str, Any], pipeline_run_id: Optional[int] = None) -> int:
        return self.upsert_source_item(item, pipeline_run_id=pipeline_run_id)

    def upsert_source_item(self, item: Dict[str, Any], pipeline_run_id: Optional[int] = None) -> int:
        dedupe_key = item.get("dedupe_key") or self.build_source_item_dedupe_key(item)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO source_items
                (pipeline_run_id, dedupe_key, source, source_item_id, url, title, summary, author, published_at,
                 metrics_json, raw_json, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                ON CONFLICT(dedupe_key) DO UPDATE SET
                    pipeline_run_id = excluded.pipeline_run_id,
                    url = excluded.url,
                    title = excluded.title,
                    summary = excluded.summary,
                    author = excluded.author,
                    published_at = excluded.published_at,
                    metrics_json = excluded.metrics_json,
                    raw_json = excluded.raw_json,
                    collected_at = excluded.collected_at
                """,
                (
                    pipeline_run_id if pipeline_run_id is not None else item.get("pipeline_run_id"),
                    dedupe_key,
                    item["source"],
                    item["source_item_id"],
                    item.get("url", ""),
                    item["title"],
                    item.get("summary", ""),
                    item.get("author", ""),
                    item.get("published_at"),
                    self.dumps(item.get("metrics_json", {})),
                    self.dumps(item.get("raw_json", {})),
                    item.get("collected_at"),
                ),
            )
            conn.commit()
            row = conn.execute("SELECT id FROM source_items WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
            return int(row["id"]) if row else int(cursor.lastrowid or -1)

    def get_source_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM source_items WHERE id = ?", (item_id,)).fetchone()
            return self._source_item_from_row(row) if row else None

    def get_recent_source_items(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM source_items ORDER BY collected_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._source_item_from_row(row) for row in rows]

    def _source_item_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["metrics_json"] = self.loads(item["metrics_json"], {})
        item["raw_json"] = self.loads(item["raw_json"], {})
        return item

    def create_signal_candidate(
        self,
        source_item_id: int,
        route_id: int,
        matched_keywords: List[str],
        status: str = "new",
        pipeline_run_id: Optional[int] = None,
        category: str = "",
    ) -> int:
        return self.upsert_signal_candidate(
            source_item_id=source_item_id,
            route_id=route_id,
            matched_keywords=matched_keywords,
            status=status,
            pipeline_run_id=pipeline_run_id,
            category=category,
        )

    def upsert_signal_candidate(
        self,
        source_item_id: int,
        route_id: int,
        matched_keywords: List[str],
        status: str = "new",
        pipeline_run_id: Optional[int] = None,
        category: str = "",
    ) -> int:
        dedupe_key = self.build_candidate_dedupe_key(source_item_id, route_id, category, matched_keywords)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO signal_candidates
                (pipeline_run_id, dedupe_key, source_item_id, route_id, score, score_breakdown_json, matched_keywords_json, status)
                VALUES (?, ?, ?, ?, 0.0, '{}', ?, ?)
                ON CONFLICT(dedupe_key) DO UPDATE SET
                    pipeline_run_id = excluded.pipeline_run_id,
                    matched_keywords_json = excluded.matched_keywords_json,
                    status = excluded.status
                """,
                (pipeline_run_id, dedupe_key, source_item_id, route_id, self.dumps(matched_keywords), status),
            )
            conn.commit()
            row = conn.execute("SELECT id FROM signal_candidates WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
            return int(row["id"]) if row else int(cursor.lastrowid or -1)

    def update_signal_candidate_score(self, candidate_id: int, score: float, score_breakdown: Dict[str, Any]):
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE signal_candidates
                SET score = ?, score_breakdown_json = ?, status = 'ranked'
                WHERE id = ?
                """,
                (float(score), self.dumps(score_breakdown), candidate_id),
            )
            conn.commit()

    def get_candidates(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = """
            SELECT
                c.*,
                i.source,
                i.source_item_id AS external_source_item_id,
                i.url,
                i.title,
                i.summary,
                i.author,
                i.published_at,
                i.metrics_json,
                i.raw_json,
                i.collected_at,
                r.source AS route_source,
                r.category AS route_category,
                r.query AS route_query
            FROM signal_candidates c
            JOIN source_items i ON i.id = c.source_item_id
            LEFT JOIN source_routes r ON r.id = c.route_id
        """
        params: List[Any] = []
        if status:
            query += " WHERE c.status = ?"
            params.append(status)
        query += " ORDER BY c.score DESC, c.created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._candidate_from_row(row) for row in rows]

    def get_candidate(self, candidate_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT
                c.*,
                i.source,
                i.source_item_id AS external_source_item_id,
                i.url,
                i.title,
                i.summary,
                i.author,
                i.published_at,
                i.metrics_json,
                i.raw_json,
                i.collected_at,
                r.source AS route_source,
                r.category AS route_category,
                r.query AS route_query
            FROM signal_candidates c
            JOIN source_items i ON i.id = c.source_item_id
            LEFT JOIN source_routes r ON r.id = c.route_id
            WHERE c.id = ?
        """
        with self.connect() as conn:
            row = conn.execute(query, (candidate_id,)).fetchone()
            return self._candidate_from_row(row) if row else None

    def get_ranked_candidates(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.get_candidates(status="ranked", limit=limit)

    def _candidate_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["matched_keywords_json"] = self.loads(item.get("matched_keywords_json"), [])
        item["score_breakdown_json"] = self.loads(item.get("score_breakdown_json"), {})
        item["metrics_json"] = self.loads(item.get("metrics_json"), {})
        item["raw_json"] = self.loads(item.get("raw_json"), {})
        return item

    def archive_today_signals(self, reason: Optional[str] = None):
        self.archive_active_signals_for_date(date.today().isoformat(), reason=reason)

    def archive_active_signals_for_date(self, signal_date: str, reason: Optional[str] = None):
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE signals
                SET status = 'archived',
                    archived_reason = ?
                WHERE signal_date = ?
                  AND status != 'archived'
                """,
                (reason, signal_date),
            )
            conn.commit()

    def get_recent_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._signal_from_row(row) for row in rows]

    def get_signal(self, signal_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
            return self._signal_from_row(row) if row else None

    def get_today_signals(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM signals
                WHERE signal_date = ?
                ORDER BY rank ASC, created_at DESC
                """,
                (date.today().isoformat(),),
            ).fetchall()
            return [self._signal_from_row(row) for row in rows]

    def get_today_active_signals(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM signals
                WHERE signal_date = ?
                  AND status IN ('active', 'saved', 'ignored', 'tracked')
                ORDER BY rank ASC, created_at DESC
                """,
                (date.today().isoformat(),),
            ).fetchall()
            return [self._signal_from_row(row) for row in rows]

    def _signal_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["source_items_json"] = self.loads(item["source_items_json"], [])
        item["metadata_json"] = self.loads(item.get("metadata_json"), {})
        if item["metadata_json"].get("briefing_version", 0) < 4:
            from src.signals.korean_briefing import build_korean_briefing
            matched = []
            with self.connect() as conn:
                candidates = conn.execute(
                    "SELECT matched_keywords_json FROM signal_candidates WHERE pipeline_run_id = ? AND source_item_id IN (SELECT id FROM source_items WHERE url = ?)",
                    (item.get("pipeline_run_id"), item.get("source_url")),
                ).fetchall()
            for candidate in candidates:
                matched.extend(self.loads(candidate["matched_keywords_json"], []))
            item["metadata_json"].update(build_korean_briefing(
                title=item.get("title", ""), summary=item.get("summary", ""),
                source=item.get("source_name", ""), category=item.get("category", ""),
                matched_keywords=list(dict.fromkeys(matched)),
            ))
            # Persist the rebuild so translation (network-bound) only runs once per row,
            # not on every subsequent read of this signal.
            with self.connect() as conn:
                conn.execute(
                    "UPDATE signals SET metadata_json = ? WHERE id = ?",
                    (self.dumps(item["metadata_json"]), item["id"]),
                )
                conn.commit()
        item["matched_keywords"] = item["metadata_json"].get("matched_keywords", [])
        for key in {
            "display_title_ko",
            "display_summary_ko",
            "why_it_matters_ko",
            "recommendation_reason_ko",
            "recommended_action_ko",
            "derived_from_ko",
            "original_title",
            "original_snippet",
            "original_language",
        }:
            item[key] = item["metadata_json"].get(key)
        return item

    def record_feedback(self, signal_id: int, event_type: str, payload: Optional[Dict[str, Any]] = None) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO feedback_events (signal_id, event_type, payload_json)
                VALUES (?, ?, ?)
                """,
                (signal_id, event_type, self.dumps(payload or {})),
            )
            if event_type in {"saved", "ignored", "tracked"}:
                conn.execute("UPDATE signals SET status = ? WHERE id = ?", (event_type, signal_id))
            conn.commit()
            return int(cursor.lastrowid)

    def get_recent_feedback_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    e.*,
                    s.title AS signal_title
                FROM feedback_events e
                LEFT JOIN signals s ON s.id = e.signal_id
                ORDER BY e.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["payload_json"] = self.loads(item["payload_json"], {})
                result.append(item)
            return result

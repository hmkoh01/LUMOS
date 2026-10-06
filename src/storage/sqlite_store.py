import json
import hashlib
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.app.config import get_database_path
from src.storage.migrations import MIGRATION_COLUMNS, SCHEMA_STATEMENTS
from src.storage.schemas import DEFAULT_CONNECTORS, DEFAULT_SOURCE_CONFIGS, DEFAULT_SOURCES

DEFAULT_LOCAL_USER_ID = 1


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
            self._migrate_legacy_user_ownership(conn)
            self._apply_column_migrations(conn)
            for statement in deferred_statements:
                conn.execute(statement)
            self._ensure_defaults(conn)
            self._remove_automatically_created_interests(conn)
            self._rebuild_fts_index(conn)
            conn.commit()

    def _migrate_legacy_user_ownership(self, conn: sqlite3.Connection):
        """Rebuild legacy singleton/config tables with per-user constraints."""
        conn.execute("INSERT OR IGNORE INTO users (id, external_id, display_name) VALUES (1, 'local-default', 'Local user')")
        specs = {
            "user_settings": (
                "CREATE TABLE user_settings_new (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1 UNIQUE, signal_count INTEGER NOT NULL DEFAULT 3, briefing_time TEXT NOT NULL DEFAULT '08:00', timezone TEXT NOT NULL DEFAULT 'Asia/Seoul', enabled_sources_json TEXT NOT NULL, enabled_connectors_json TEXT NOT NULL, desktop_push_enabled INTEGER NOT NULL DEFAULT 1, generate_mode TEXT NOT NULL DEFAULT 'mock', sync_before_briefing INTEGER NOT NULL DEFAULT 1, auto_expand_interests INTEGER NOT NULL DEFAULT 0, context_sync_interval_minutes INTEGER NOT NULL DEFAULT 360, max_interest_keywords INTEGER NOT NULL DEFAULT 50, mode_enabled INTEGER NOT NULL DEFAULT 1, onboarding_completed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "INSERT INTO user_settings_new (id, user_id, signal_count, briefing_time, timezone, enabled_sources_json, enabled_connectors_json, desktop_push_enabled, generate_mode, sync_before_briefing, auto_expand_interests, context_sync_interval_minutes, max_interest_keywords, mode_enabled, onboarding_completed, created_at, updated_at) SELECT id, 1, signal_count, briefing_time, timezone, enabled_sources_json, enabled_connectors_json, desktop_push_enabled, generate_mode, sync_before_briefing, auto_expand_interests, context_sync_interval_minutes, max_interest_keywords, mode_enabled, onboarding_completed, created_at, updated_at FROM user_settings",
            ),
            "user_profile": (
                "CREATE TABLE user_profile_new (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1 UNIQUE, role TEXT NOT NULL DEFAULT '', role_detail TEXT NOT NULL DEFAULT '', goals_json TEXT NOT NULL DEFAULT '[]', interest_types_json TEXT NOT NULL DEFAULT '[]', raw_onboarding_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "INSERT INTO user_profile_new (id, user_id, role, role_detail, goals_json, interest_types_json, raw_onboarding_json, created_at, updated_at) SELECT id, 1, role, role_detail, goals_json, interest_types_json, raw_onboarding_json, created_at, updated_at FROM user_profile",
            ),
            "interest_graph": (
                "CREATE TABLE interest_graph_new (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1, keyword TEXT NOT NULL, category TEXT, weight REAL NOT NULL DEFAULT 1.0, source TEXT NOT NULL DEFAULT 'manual', evidence_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'active', last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, keyword, category, source))",
                "INSERT INTO interest_graph_new (id, user_id, keyword, category, weight, source, evidence_json, status, last_seen_at, created_at, updated_at) SELECT id, 1, keyword, category, weight, source, evidence_json, status, last_seen_at, created_at, updated_at FROM interest_graph",
            ),
            "source_configs": (
                "CREATE TABLE source_configs_new (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1, source_id TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, display_name TEXT NOT NULL DEFAULT '', config_json TEXT NOT NULL DEFAULT '{}', priority INTEGER NOT NULL DEFAULT 50, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, source_id))",
                "INSERT INTO source_configs_new (id, user_id, source_id, enabled, display_name, config_json, priority, created_at, updated_at) SELECT id, 1, source_id, enabled, display_name, config_json, priority, created_at, updated_at FROM source_configs",
            ),
            "connectors": (
                "CREATE TABLE connectors_new (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1, connector_type TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, auth_status TEXT NOT NULL DEFAULT 'not_connected', config_json TEXT NOT NULL DEFAULT '{}', last_sync_at TEXT, last_status TEXT, last_error TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, connector_type))",
                "INSERT INTO connectors_new (id, user_id, connector_type, enabled, auth_status, config_json, last_sync_at, last_status, last_error, created_at, updated_at) SELECT id, 1, connector_type, enabled, auth_status, config_json, last_sync_at, last_status, last_error, created_at, updated_at FROM connectors",
            ),
            "context_items": (
                "CREATE TABLE context_items_new (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1, connector_type TEXT NOT NULL, item_id TEXT NOT NULL, dedupe_key TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', text_snippet TEXT NOT NULL DEFAULT '', url TEXT, path TEXT, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT, updated_at TEXT, collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, dedupe_key))",
                "INSERT INTO context_items_new (id, user_id, connector_type, item_id, dedupe_key, title, text_snippet, url, path, metadata_json, created_at, updated_at, collected_at) SELECT id, 1, connector_type, item_id, dedupe_key, title, text_snippet, url, path, metadata_json, created_at, updated_at, collected_at FROM context_items",
            ),
            "context_sync_runs": (
                "CREATE TABLE context_sync_runs_new (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1, connector_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'running', started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT, item_count INTEGER NOT NULL DEFAULT 0, keyword_count INTEGER NOT NULL DEFAULT 0, summary_json TEXT NOT NULL DEFAULT '{}', error_message TEXT)",
                "INSERT INTO context_sync_runs_new (id, user_id, connector_type, status, started_at, completed_at, item_count, keyword_count, summary_json, error_message) SELECT id, 1, connector_type, status, started_at, completed_at, item_count, keyword_count, summary_json, error_message FROM context_sync_runs",
            ),
        }
        for table, (create_sql, copy_sql) in specs.items():
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "user_id" in columns:
                continue
            conn.execute(create_sql)
            conn.execute(copy_sql)
            old_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            new_count = conn.execute(f"SELECT COUNT(*) FROM {table}_new").fetchone()[0]
            if old_count != new_count:
                raise RuntimeError(f"ownership migration verification failed for {table}")
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")

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
        self._seed_default_connectors(conn, DEFAULT_LOCAL_USER_ID)
        self._seed_default_source_configs(conn, overwrite=False)

    def _seed_default_connectors(self, conn: sqlite3.Connection, user_id: int):
        for connector_type, enabled in DEFAULT_CONNECTORS.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO connectors
                (user_id, connector_type, enabled, auth_status, config_json)
                VALUES (?, ?, ?, 'not_connected', '{}')
                """,
                (user_id, connector_type, 1 if enabled else 0),
            )

    def _ensure_user_settings(self, conn: sqlite3.Connection, user_id: int):
        """Create a settings row lazily for a known user without touching other domains."""
        conn.execute(
            """
            INSERT OR IGNORE INTO user_settings
            (user_id, signal_count, briefing_time, timezone, enabled_sources_json,
             enabled_connectors_json, desktop_push_enabled, generate_mode, sync_before_briefing,
             context_sync_interval_minutes, max_interest_keywords, mode_enabled, onboarding_completed)
            VALUES (?, 3, '08:00', 'Asia/Seoul', ?, ?, 1, 'mock', 1, 360, 50, 1, 0)
            """,
            (user_id, self.dumps(DEFAULT_SOURCES), self.dumps(DEFAULT_CONNECTORS)),
        )

    def _remove_automatically_created_interests(self, conn: sqlite3.Connection):
        """Keep the interest graph limited to terms the user explicitly chose."""
        conn.execute("DELETE FROM interest_graph WHERE source IN ('feedback', 'browser_history', 'local_files')")
        conn.execute("UPDATE user_settings SET auto_expand_interests = 0 WHERE id = 1")

    def _seed_default_source_configs(self, conn: sqlite3.Connection, overwrite: bool = False, user_id: int = DEFAULT_LOCAL_USER_ID):
        for source_id, config in DEFAULT_SOURCE_CONFIGS.items():
            if overwrite:
                conn.execute(
                    """
                    INSERT INTO source_configs
                    (user_id, source_id, enabled, display_name, config_json, priority, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id, source_id) DO UPDATE SET
                        enabled = excluded.enabled,
                        display_name = excluded.display_name,
                        config_json = excluded.config_json,
                        priority = excluded.priority,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        user_id, source_id,
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
                    (user_id, source_id, enabled, display_name, config_json, priority)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, source_id,
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

    # ------------------------------------------------------------------
    # External identity → internal user mapping
    # ------------------------------------------------------------------

    def get_or_create_user_by_external_id(
        self, external_id: str, display_name: str = ""
    ) -> int:
        """Return the internal INTEGER id for an external auth identity.

        On first login, inserts a new users row. Concurrent first-logins for
        the same external_id are safe: the UNIQUE constraint on external_id
        causes the losing INSERT OR IGNORE to be a no-op, and the subsequent
        SELECT always returns the winning row.
        """
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (external_id, display_name) VALUES (?, ?)",
                (external_id, display_name),
            )
            row = conn.execute(
                "SELECT id FROM users WHERE external_id = ?", (external_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError(
                f"User lookup failed for external_id={external_id!r} after insert"
            )
        return int(row[0])

    def get_user_by_external_id(self, external_id: str) -> Optional[Dict[str, Any]]:
        """Return the users row for an external_id, or None if not found."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, external_id, display_name, created_at FROM users WHERE external_id = ?",
                (external_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_settings(self, user_id: int = DEFAULT_LOCAL_USER_ID) -> Dict[str, Any]:
        with self.connect() as conn:
            self._ensure_defaults(conn)
            self._ensure_user_settings(conn, user_id)
            row = conn.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
            result = dict(row)
            result.pop("auto_expand_interests", None)
            result["enabled_sources_json"] = self.loads(result["enabled_sources_json"], DEFAULT_SOURCES)
            result["enabled_connectors_json"] = self.loads(result["enabled_connectors_json"], DEFAULT_CONNECTORS)
            result["desktop_push_enabled"] = bool(result["desktop_push_enabled"])
            result["sync_before_briefing"] = bool(result.get("sync_before_briefing", 1))
            result["mode_enabled"] = bool(result["mode_enabled"])
            result["onboarding_completed"] = bool(result["onboarding_completed"])
            return result

    def update_settings(self, updates: Dict[str, Any], user_id: int = DEFAULT_LOCAL_USER_ID) -> Dict[str, Any]:
        allowed = {
            "signal_count",
            "briefing_time",
            "timezone",
            "enabled_sources_json",
            "enabled_connectors_json",
            "desktop_push_enabled",
            "generate_mode",
            "sync_before_briefing",
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
            elif key in {"desktop_push_enabled", "sync_before_briefing", "mode_enabled", "onboarding_completed"}:
                value = 1 if bool(value) else 0
            assignments.append(f"{key} = ?")
            params.append(value)

        if assignments:
            assignments.append("updated_at = CURRENT_TIMESTAMP")
            params.append(user_id)
            with self.connect() as conn:
                self._ensure_defaults(conn)
                self._ensure_user_settings(conn, user_id)
                conn.execute(f"UPDATE user_settings SET {', '.join(assignments)} WHERE user_id = ?", params)
                conn.commit()
        return self.get_settings(user_id)

    def seed_default_source_configs(self, overwrite: bool = False, user_id: int = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            self._seed_default_source_configs(conn, overwrite=overwrite, user_id=user_id)
            conn.commit()
        return self.get_source_configs(user_id=user_id)

    def get_source_configs(self, user_id: int = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            self._seed_default_source_configs(conn, overwrite=False, user_id=user_id)
            rows = conn.execute(
                """
                SELECT * FROM source_configs WHERE user_id = ?
                ORDER BY enabled DESC, priority DESC, source_id ASC
                """, (user_id,)
            ).fetchall()
            return [self._source_config_from_row(row) for row in rows]

    def get_source_config(self, source_id: str, user_id: int = DEFAULT_LOCAL_USER_ID) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            self._seed_default_source_configs(conn, overwrite=False, user_id=user_id)
            row = conn.execute("SELECT * FROM source_configs WHERE source_id = ? AND user_id = ?", (source_id, user_id)).fetchone()
            return self._source_config_from_row(row) if row else None

    def get_enabled_source_configs(self, user_id: int = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
        return [config for config in self.get_source_configs(user_id=user_id) if config["enabled"]]

    def upsert_source_config(
        self,
        source_id: str,
        enabled: Optional[bool] = None,
        priority: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
        display_name: Optional[str] = None,
        user_id: int = DEFAULT_LOCAL_USER_ID,
    ) -> Dict[str, Any]:
        existing = self.get_source_config(source_id, user_id=user_id) or {
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
                (user_id, source_id, enabled, display_name, config_json, priority, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, source_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    display_name = excluded.display_name,
                    config_json = excluded.config_json,
                    priority = excluded.priority,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id, source_id,
                    1 if next_enabled else 0,
                    next_display_name,
                    self.dumps(next_config),
                    next_priority,
                ),
            )
            conn.commit()
        return self.get_source_config(source_id, user_id=user_id) or {}

    def _source_config_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        item["config_json"] = self.loads(item["config_json"], {})
        return item

    def get_profile(self, user_id: int = DEFAULT_LOCAL_USER_ID) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM user_profile WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["goals_json"] = self.loads(result["goals_json"], [])
            result["interest_types_json"] = self.loads(result["interest_types_json"], [])
            result["raw_onboarding_json"] = self.loads(result["raw_onboarding_json"], {})
            return result

    def upsert_profile(self, profile: Dict[str, Any], user_id: int = DEFAULT_LOCAL_USER_ID) -> Dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_profile
                (user_id, role, role_detail, goals_json, interest_types_json, raw_onboarding_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    role = excluded.role,
                    role_detail = excluded.role_detail,
                    goals_json = excluded.goals_json,
                    interest_types_json = excluded.interest_types_json,
                    raw_onboarding_json = excluded.raw_onboarding_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id, profile.get("role", ""),
                    profile.get("role_detail", ""),
                    self.dumps(profile.get("goals", [])),
                    self.dumps(profile.get("interest_types", [])),
                    self.dumps(profile.get("raw_onboarding", {})),
                ),
            )
            conn.commit()
        return self.get_profile(user_id) or {}

    def get_connectors(self, user_id: int = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            self._ensure_defaults(conn)
            self._ensure_user_settings(conn, user_id)
            self._seed_default_connectors(conn, user_id)
            rows = conn.execute(
                "SELECT * FROM connectors WHERE user_id = ? ORDER BY connector_type ASC", (user_id,)
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["enabled"] = bool(item["enabled"])
                item["config_json"] = self.loads(item["config_json"], {})
                result.append(item)
            return result

    def get_connector(
        self, connector_type: str, user_id: int = DEFAULT_LOCAL_USER_ID
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            self._ensure_defaults(conn)
            self._ensure_user_settings(conn, user_id)
            self._seed_default_connectors(conn, user_id)
            row = conn.execute(
                "SELECT * FROM connectors WHERE user_id = ? AND connector_type = ?", (user_id, connector_type)
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["enabled"] = bool(result["enabled"])
            result["config_json"] = self.loads(result["config_json"], {})
            return result

    def update_connector(
        self,
        connector_type: str,
        enabled: bool,
        config: Optional[Dict[str, Any]] = None,
        user_id: int = DEFAULT_LOCAL_USER_ID,
    ):
        if connector_type not in DEFAULT_CONNECTORS:
            raise ValueError(f"Unsupported connector_type: {connector_type}")
        with self.connect() as conn:
            self._ensure_defaults(conn)
            self._ensure_user_settings(conn, user_id)
            self._seed_default_connectors(conn, user_id)
            conn.execute(
                """
                INSERT INTO connectors (user_id, connector_type, enabled, config_json, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, connector_type) DO UPDATE SET
                    enabled = excluded.enabled,
                    config_json = excluded.config_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, connector_type, 1 if enabled else 0, self.dumps(config or {})),
            )
            conn.commit()

        settings = self.get_settings(user_id=user_id)
        connector_map = settings["enabled_connectors_json"]
        connector_map[connector_type] = enabled
        self.update_settings({"enabled_connectors_json": connector_map}, user_id=user_id)
        return self.get_connector(connector_type, user_id=user_id) or {}

    def update_connector_sync_status(
        self,
        connector_type: str,
        status: str,
        error: Optional[str] = None,
        user_id: int = DEFAULT_LOCAL_USER_ID,
    ):
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE connectors
                SET last_sync_at = CURRENT_TIMESTAMP,
                    last_status = ?,
                    last_error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE connector_type = ? AND user_id = ?
                """,
                (status, error, connector_type, user_id),
            )
            conn.commit()

    def upsert_interest(self, keyword: str, category: Optional[str], weight: float, source: str, evidence: Dict[str, Any], user_id: int = DEFAULT_LOCAL_USER_ID):
        keyword = keyword.strip()
        if not keyword:
            return
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO interest_graph
                (user_id, keyword, category, weight, source, evidence_json, status, last_seen_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, keyword, category, source) DO UPDATE SET
                    weight = MAX(interest_graph.weight, excluded.weight),
                    evidence_json = excluded.evidence_json,
                    last_seen_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, keyword, category, float(weight), source, self.dumps(evidence)),
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

    def update_interest(self, keyword: str, updates: Dict[str, Any] = None, user_id: int = DEFAULT_LOCAL_USER_ID, **kwargs) -> Optional[Dict[str, Any]]:
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
            params.extend([keyword, user_id])
            conn.execute(f"UPDATE interest_graph SET {', '.join(assignments)} WHERE keyword = ? AND user_id = ?", params)
            conn.commit()
        matches = [item for item in self.get_interests(limit=500, include_muted=True, user_id=user_id) if item["keyword"] == keyword]
        return matches[0] if matches else None

    def add_manual_interest(self, keyword: str, user_id: int = DEFAULT_LOCAL_USER_ID) -> Dict[str, Any]:
        keyword = " ".join(keyword.split())
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id FROM interest_graph WHERE keyword = ? COLLATE NOCASE AND user_id = ? ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, id LIMIT 1",
                (keyword, user_id),
            ).fetchone()
            if row:
                interest_id = row["id"]
                conn.execute("UPDATE interest_graph SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?", (interest_id, user_id))
            else:
                cursor = conn.execute(
                    "INSERT INTO interest_graph (user_id, keyword, category, weight, source, evidence_json, status, last_seen_at, updated_at) VALUES (?, ?, 'manual', 1, 'manual', ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (user_id, keyword, self.dumps({"added_by": "user"})),
                )
                interest_id = cursor.lastrowid
            conn.execute("UPDATE user_settings SET onboarding_completed = 1 WHERE user_id = ?", (user_id,))
            result = dict(conn.execute("SELECT * FROM interest_graph WHERE id = ? AND user_id = ?", (interest_id, user_id)).fetchone())
            result["evidence_json"] = self.loads(result["evidence_json"], {})
            conn.commit()
            return result

    def delete_interest(self, keyword: str, user_id: int = DEFAULT_LOCAL_USER_ID) -> int:
        return 1 if self.update_interest(keyword, status="deleted", user_id=user_id) else 0

    def hard_delete_interest(self, keyword: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM interest_graph WHERE keyword = ?", (keyword,))
            conn.commit()
            return int(cursor.rowcount)

    def mute_interest(self, keyword: str, user_id: int = DEFAULT_LOCAL_USER_ID) -> Optional[Dict[str, Any]]:
        return self.update_interest(keyword, status="muted", user_id=user_id)

    def unmute_interest(self, keyword: str, user_id: int = DEFAULT_LOCAL_USER_ID) -> Optional[Dict[str, Any]]:
        return self.update_interest(keyword, status="active", user_id=user_id)

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
        user_id: int = DEFAULT_LOCAL_USER_ID,
    ) -> List[Dict[str, Any]]:
        clauses = ["user_id = ?"]
        params: List[Any] = [user_id]
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
                ORDER BY CASE WHEN status = 'muted' THEN 1 ELSE 0 END,
                         id ASC
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
        interests = self.get_interests(status="active", limit=None)
        return sorted(interests, key=lambda item: (-float(item.get("weight") or 0), item["id"]))[:limit]

    def get_interest_evidence(
        self, keyword: str, user_id: int = DEFAULT_LOCAL_USER_ID
    ) -> List[Dict[str, Any]]:
        return [
            item
            for item in self.get_interests(limit=None, include_muted=True, user_id=user_id)
            if item["keyword"] == keyword
        ]

    def prune_interests(
        self, max_keywords: int, user_id: int = DEFAULT_LOCAL_USER_ID
    ) -> Dict[str, Any]:
        active = sorted(
            self.get_interests(status="active", limit=None, user_id=user_id),
            key=lambda item: (-float(item.get("weight") or 0), item["id"]),
        )
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
            self.mute_interest(item["keyword"], user_id=user_id)
            muted.append(item["keyword"])
        return {"muted": muted, "kept": max_keywords}

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

    def upsert_context_item(
        self, item: Dict[str, Any], user_id: int = DEFAULT_LOCAL_USER_ID
    ) -> int:
        dedupe_key = item.get("dedupe_key") or self.build_context_item_dedupe_key(item)
        snippet = str(item.get("text_snippet") or item.get("text") or "")[:1000]
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO context_items
                (user_id, connector_type, item_id, dedupe_key, title, text_snippet, url, path, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, dedupe_key) DO UPDATE SET
                    title = excluded.title,
                    text_snippet = excluded.text_snippet,
                    url = excluded.url,
                    path = excluded.path,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at,
                    collected_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
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
            row = conn.execute(
                "SELECT id FROM context_items WHERE user_id = ? AND dedupe_key = ?", (user_id, dedupe_key)
            ).fetchone()
            return int(row["id"]) if row else int(cursor.lastrowid or -1)

    def get_context_items(
        self,
        connector_type: Optional[str] = None,
        limit: int = 50,
        user_id: int = DEFAULT_LOCAL_USER_ID,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM context_items WHERE user_id = ?"
        params: List[Any] = [user_id]
        if connector_type:
            query += " AND connector_type = ?"
            params.append(connector_type)
        if search:
            query += " AND (title LIKE ? OR text_snippet LIKE ? OR url LIKE ? OR path LIKE ?)"
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern, pattern])
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

    def delete_context_item(self, item_id: int, user_id: int = DEFAULT_LOCAL_USER_ID) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM context_items WHERE id = ? AND user_id = ?", (item_id, user_id))
            conn.commit()
            return cursor.rowcount > 0

    def clear_context_items(
        self, connector_type: Optional[str] = None, user_id: int = DEFAULT_LOCAL_USER_ID
    ) -> int:
        query = "DELETE FROM context_items WHERE user_id = ?"
        params: List[Any] = [user_id]
        if connector_type:
            query += " AND connector_type = ?"
            params.append(connector_type)
        with self.connect() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return int(cursor.rowcount)

    def create_context_sync_run(
        self, connector_type: str, user_id: int = DEFAULT_LOCAL_USER_ID
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO context_sync_runs (user_id, connector_type) VALUES (?, ?)",
                (user_id, connector_type),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def complete_context_sync_run(
        self,
        run_id: int,
        item_count: int = 0,
        keyword_count: int = 0,
        summary: Optional[Dict[str, Any]] = None,
        user_id: int = DEFAULT_LOCAL_USER_ID,
    ) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE context_sync_runs
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP,
                    item_count = ?, keyword_count = ?, summary_json = ?
                WHERE id = ? AND user_id = ?
                """,
                (item_count, keyword_count, self.dumps(summary or {}), run_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def fail_context_sync_run(
        self, run_id: int, error_message: str, user_id: int = DEFAULT_LOCAL_USER_ID
    ) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE context_sync_runs
                SET status = 'failed', completed_at = CURRENT_TIMESTAMP, error_message = ?
                WHERE id = ? AND user_id = ?
                """,
                (error_message, run_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_context_sync_run(
        self, run_id: int, user_id: int = DEFAULT_LOCAL_USER_ID
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM context_sync_runs WHERE id = ? AND user_id = ?", (run_id, user_id)
            ).fetchone()
            return self._context_sync_run_from_row(row) if row else None

    def get_recent_context_sync_runs(
        self, limit: int = 20, user_id: int = DEFAULT_LOCAL_USER_ID
    ) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM context_sync_runs WHERE user_id = ? ORDER BY started_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [self._context_sync_run_from_row(row) for row in rows]

    def _context_sync_run_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        result = dict(row)
        result["summary_json"] = self.loads(result.get("summary_json"), {})
        return result

    def create_pipeline_run(
        self,
        run_type: str,
        triggered_by: str = "manual",
        settings_snapshot: Optional[Dict[str, Any]] = None,
        profile_snapshot: Optional[Dict[str, Any]] = None,
        interest_snapshot: Optional[List[Dict[str, Any]]] = None,
        selected_sources: Optional[List[str]] = None,
        user_id: int = DEFAULT_LOCAL_USER_ID,
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO pipeline_runs
                (user_id, run_type, status, triggered_by, settings_snapshot_json,
                 profile_snapshot_json, interest_snapshot_json, selected_sources_json)
                VALUES (?, ?, 'running', ?, ?, ?, ?, ?)
                """,
                (
                    user_id, run_type,
                    triggered_by,
                    self.dumps(settings_snapshot or {}),
                    self.dumps(profile_snapshot or {}),
                    self.dumps(interest_snapshot or []),
                    self.dumps(selected_sources or []),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def complete_pipeline_run(self, run_id: int, summary: Dict[str, Any], user_id: int = DEFAULT_LOCAL_USER_ID):
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
                    WHERE id = ? AND user_id = ?
                    """,
                    (self.dumps(summary), self.dumps(selected_sources), run_id, user_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE pipeline_runs
                    SET status = 'completed',
                        completed_at = CURRENT_TIMESTAMP,
                        summary_json = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (self.dumps(summary), run_id, user_id),
                )
            conn.commit()

    def fail_pipeline_run(self, run_id: int, error_message: str, user_id: int = DEFAULT_LOCAL_USER_ID):
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE pipeline_runs
                SET status = 'failed',
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = ?
                WHERE id = ? AND user_id = ?
                """,
                (error_message, run_id, user_id),
            )
            conn.commit()

    def get_pipeline_run(self, run_id: int, user_id: int = DEFAULT_LOCAL_USER_ID) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM pipeline_runs WHERE id = ? AND user_id = ?", (run_id, user_id)).fetchone()
            if not row:
                return None
            run = self._pipeline_run_from_row(row)
            run.update(self._pipeline_run_counts(conn, run_id))
            return run

    def get_recent_pipeline_runs(self, limit: int = 10, user_id: int = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pipeline_runs WHERE user_id = ? ORDER BY started_at DESC LIMIT ?",
                (user_id, limit),
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

    def create_signal(self, signal: Dict[str, Any], pipeline_run_id: Optional[int] = None, user_id: int = DEFAULT_LOCAL_USER_ID) -> int:
        with self.connect() as conn:
            signal_id = self._insert_signal(conn, signal, pipeline_run_id, user_id)
            conn.commit()
            return signal_id

    def _insert_signal(self, conn, signal, pipeline_run_id=None, user_id=DEFAULT_LOCAL_USER_ID):
        signal_date = signal.get("signal_date") or date.today().isoformat()
        dedupe_key = signal.get("dedupe_key") or self.build_signal_dedupe_key(signal)
        cursor = conn.execute(
            """
            INSERT INTO signals
            (user_id, pipeline_run_id, dedupe_key, signal_date, title, summary, why_it_matters, category, recommended_action,
             source_name, source_url, source_items_json, metadata_json, confidence, rank, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, pipeline_run_id if pipeline_run_id is not None else signal.get("pipeline_run_id"),
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
        return int(cursor.lastrowid)

    def save_signal_reserves(self, run_id, candidates, base_count, user_id: int = DEFAULT_LOCAL_USER_ID):
        # Snapshot the ranked result: later collections can update candidate/source rows.
        with self.connect() as conn:
            if not self._pipeline_run_owned(conn, run_id, user_id):
                raise ValueError("Pipeline run not found for this user")
            conn.executemany(
                "INSERT INTO signal_reserves (pipeline_run_id, rank, candidate_json) VALUES (?, ?, ?)",
                [(run_id, rank, self.dumps(candidate))
                 for rank, candidate in enumerate(candidates, start=base_count + 1)],
            )

    def signal_expansion_status(self, user_id: int = DEFAULT_LOCAL_USER_ID):
        with self.connect() as conn:
            return self._expansion_status(conn, user_id)

    def _expansion_status(self, conn, user_id: int = DEFAULT_LOCAL_USER_ID):
        row = conn.execute(
            "SELECT MAX(pipeline_run_id) AS run_id FROM signals WHERE user_id = ? AND signal_date = ? AND status != 'archived'",
            (user_id, date.today().isoformat()),
        ).fetchone()
        run_id = row["run_id"]
        remaining = conn.execute(
            "SELECT COUNT(*) FROM signal_reserves WHERE pipeline_run_id = ? AND signal_id IS NULL", (run_id,),
        ).fetchone()[0]
        return {"pipeline_run_id": run_id, "has_more": remaining > 0}

    def get_signal_reserves(self, run_id, limit=3, user_id: int = DEFAULT_LOCAL_USER_ID):
        with self.connect() as conn:
            if not self._pipeline_run_owned(conn, run_id, user_id):
                return []
            rows = conn.execute(
                "SELECT rank, candidate_json FROM signal_reserves WHERE pipeline_run_id = ? "
                "AND signal_id IS NULL ORDER BY rank LIMIT ?", (run_id, limit),
            ).fetchall()
        return [(row["rank"], self.loads(row["candidate_json"], {})) for row in rows]

    def reveal_signals(self, run_id, prepared, user_id: int = DEFAULT_LOCAL_USER_ID):
        from src.signals.identity import article_key
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not self._pipeline_run_owned(conn, run_id, user_id) or self._expansion_status(conn, user_id)["pipeline_run_id"] != run_id:
                raise ValueError("브리핑이 바뀌었어요. 새로고침 후 다시 시도해주세요.")
            shown = conn.execute(
                "SELECT id, source_url FROM signals WHERE user_id = ? AND signal_date = ? AND status != 'archived'",
                (user_id, date.today().isoformat()),
            ).fetchall()
            identities = {article_key(dict(row)): row["id"] for row in shown}
            for rank, signal in prepared:
                reserve = conn.execute(
                    "SELECT signal_id FROM signal_reserves WHERE pipeline_run_id = ? AND rank = ?", (run_id, rank),
                ).fetchone()
                if not reserve or reserve["signal_id"] is not None:
                    continue
                identity = article_key(signal)
                signal_id = identities.get(identity)
                if signal_id is None:
                    signal_id = self._insert_signal(conn, signal, run_id, user_id)
                    identities[identity] = signal_id
                conn.execute("UPDATE signal_reserves SET signal_id = ? WHERE pipeline_run_id = ? AND rank = ?",
                             (signal_id, run_id, rank))
            conn.commit()

    @staticmethod
    def _pipeline_run_owned(conn: sqlite3.Connection, run_id: int, user_id: int) -> bool:
        return bool(conn.execute("SELECT 1 FROM pipeline_runs WHERE id = ? AND user_id = ?", (run_id, user_id)).fetchone())

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

    def archive_today_signals(
        self, reason: Optional[str] = None, user_id: int = DEFAULT_LOCAL_USER_ID
    ):
        self.archive_active_signals_for_date(date.today().isoformat(), reason=reason, user_id=user_id)

    def archive_active_signals_for_date(
        self, signal_date: str, reason: Optional[str] = None, user_id: int = DEFAULT_LOCAL_USER_ID
    ):
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE signals
                SET status = 'archived',
                    archived_reason = ?
                WHERE signal_date = ?
                  AND user_id = ?
                  AND status NOT IN ('archived', 'saved')
                """,
                (reason, signal_date, user_id),
            )
            conn.commit()

    def get_recent_signals(
        self, limit: int = 50, user_id: int = DEFAULT_LOCAL_USER_ID
    ) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM signals WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [self._signal_from_row(row) for row in rows]

    def get_signal(self, signal_id: int, user_id: int = DEFAULT_LOCAL_USER_ID) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM signals WHERE id = ? AND user_id = ?", (signal_id, user_id)).fetchone()
            return self._signal_from_row(row) if row else None

    def get_saved_signals(self, limit: int = 100, user_id: int = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT signals.*, MAX(feedback_events.created_at) AS saved_at
                FROM signals
                LEFT JOIN feedback_events
                  ON feedback_events.signal_id = signals.id AND feedback_events.event_type = 'saved' AND feedback_events.user_id = ?
                WHERE signals.status = 'saved' AND signals.user_id = ?
                GROUP BY signals.id
                ORDER BY saved_at DESC, signals.created_at DESC
                LIMIT ?
                """,
                (user_id, user_id, limit),
            ).fetchall()
            return [self._signal_from_row(row) for row in rows]

    def delete_saved_signal(self, signal_id: int, user_id: int = DEFAULT_LOCAL_USER_ID) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM signals WHERE id = ? AND user_id = ? AND status = 'saved'", (signal_id, user_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_feedback_signals(self, event_type: str, limit: int = 100, user_id: int = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
        if event_type not in {"ignored", "tracked"}:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.*, e.created_at AS feedback_at
                FROM feedback_events e
                JOIN signals s ON s.id = e.signal_id
                WHERE e.event_type = ? AND e.user_id = ? AND s.user_id = ?
                  AND e.id = (
                    SELECT latest.id FROM feedback_events latest
                    WHERE latest.signal_id = e.signal_id AND latest.user_id = ?
                      AND latest.event_type IN ('ignored', 'tracked')
                    ORDER BY latest.id DESC LIMIT 1
                  )
                ORDER BY feedback_at DESC
                LIMIT ?
                """,
                (event_type, user_id, user_id, user_id, limit),
            ).fetchall()
            return [self._signal_from_row(row) for row in rows]

    def clear_feedback_signal(self, signal_id: int, event_type: str, user_id: int = DEFAULT_LOCAL_USER_ID) -> bool:
        if event_type not in {"ignored", "tracked"}:
            return False
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM feedback_events WHERE signal_id = ? AND event_type = ? AND user_id = ?",
                (signal_id, event_type, user_id),
            )
            if cursor.rowcount:
                row = conn.execute("SELECT status, signal_date FROM signals WHERE id = ? AND user_id = ?", (signal_id, user_id)).fetchone()
                if row and row["status"] == event_type:
                    next_status = "active" if row["signal_date"] == date.today().isoformat() else "archived"
                    conn.execute("UPDATE signals SET status = ? WHERE id = ? AND user_id = ?", (next_status, signal_id, user_id))
            conn.commit()
            return cursor.rowcount > 0

    def has_feedback_signal(self, signal_id: int, event_type: str, user_id: int = DEFAULT_LOCAL_USER_ID) -> bool:
        if event_type not in {"saved", "ignored", "tracked"}:
            return False
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM feedback_events WHERE signal_id = ? AND event_type = ? AND user_id = ? LIMIT 1",
                (signal_id, event_type, user_id),
            ).fetchone()
            return bool(row)

    def get_today_signals(self, include_archived: bool = True, user_id: int = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM signals
                WHERE user_id = ? AND signal_date = ?
                  AND (? OR status != 'archived')
                ORDER BY rank ASC, created_at DESC
                """,
                (user_id, date.today().isoformat(), include_archived),
            ).fetchall()
        signals = self._dedupe_signal_articles(rows)
        # A daily briefing is a snapshot.  Do not re-evaluate it against the
        # current interest graph when it is loaded again: feedback and interest
        # changes affect future recommendations, but must not make an already
        # shown card disappear from today's list.
        return signals if include_archived else [signal for signal in signals if signal.get("status") != "archived"]

    def get_today_active_signals(self, user_id: int = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM signals
                WHERE user_id = ? AND signal_date = ?
                  AND status IN ('active', 'saved', 'ignored', 'tracked')
                ORDER BY rank ASC, created_at DESC
                """,
                (user_id, date.today().isoformat()),
            ).fetchall()
        active = [signal for signal in self._dedupe_signal_articles(rows) if signal.get("status") != "archived"]
        # The interest graph selects candidates before a signal is stored. A
        # briefing is then a snapshot: re-filtering against the current graph
        # can make valid cards disappear after interests change or are empty.
        # Keep this consistent with /signals/today and rolling period queries.
        return active

    def get_signals_for_period(
        self,
        period: str,
        now: Optional[datetime] = None,
        user_id: int = DEFAULT_LOCAL_USER_ID,
    ) -> List[Dict[str, Any]]:
        """Return non-archived signals in a rolling content-time window.

        Signal rows deliberately remain snapshots.  For a cross-briefing view we
        prefer the original article's published timestamp, then fall back to
        the signal creation time when provenance does not contain one.
        """
        window_days = {"today": 1, "week": 7, "month": 30}
        if period not in window_days:
            raise ValueError(f"Unsupported briefing period: {period}")
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        cutoff = reference - timedelta(days=window_days[period])
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM signals WHERE user_id = ? AND status != 'archived'", (user_id,)
            ).fetchall()

        candidates = []
        for row in rows:
            signal = self._signal_from_row(row)
            content_time = self._signal_content_time(signal)
            if content_time and content_time >= cutoff:
                signal["content_timestamp"] = content_time.isoformat().replace("+00:00", "Z")
                candidates.append(signal)

        # Highest relevance first; the source content time makes equally ranked
        # cards deterministic and keeps newer developments at the top.
        candidates.sort(
            key=lambda signal: (
                -float(signal.get("confidence") or 0),
                -self._signal_content_time(signal).timestamp(),
                -int(signal.get("id") or 0),
            )
        )
        return self._dedupe_signal_articles_from_signals(candidates)

    def _signal_content_time(self, signal: Dict[str, Any]) -> Optional[datetime]:
        metadata = signal.get("metadata_json") or {}
        source_items = signal.get("source_items_json") or []
        values = [
            metadata.get("published_at"),
            *(item.get("published_at") for item in source_items if isinstance(item, dict)),
            signal.get("created_at"),
        ]
        for value in values:
            parsed = self._parse_utc_timestamp(value)
            if parsed:
                return parsed
        return None

    @staticmethod
    def _parse_utc_timestamp(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            normalized = str(value).strip().replace(" ", "T")
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    def _dedupe_signal_articles(self, rows) -> List[Dict[str, Any]]:
        from src.signals.identity import article_key

        signals = []
        seen = set()
        for row in rows:
            signal = self._signal_from_row(row)
            identity = article_key({**signal, "source": signal.get("source_name", "")})
            if identity in seen:
                continue
            seen.add(identity)
            signals.append(signal)
        return signals

    @staticmethod
    def _dedupe_signal_articles_from_signals(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        from src.signals.identity import article_key

        unique = []
        seen = set()
        for signal in signals:
            identity = article_key({**signal, "source": signal.get("source_name", "")})
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(signal)
        return unique

    def _filter_signals_by_active_interests(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        active_keywords = {
            str(interest.get("keyword", "")).strip().casefold()
            for interest in self.get_interests(status="active", limit=None)
            if str(interest.get("keyword", "")).strip()
        }
        visible = []
        for signal in signals:
            matched = [str(keyword).strip().casefold() for keyword in signal.get("matched_keywords", []) if str(keyword).strip()]
            if matched and not any(keyword in active_keywords for keyword in matched):
                continue
            visible.append(signal)
        return visible

    def _signal_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["source_items_json"] = self.loads(item["source_items_json"], [])
        item["metadata_json"] = self.loads(item.get("metadata_json"), {})
        if item["metadata_json"].get("briefing_version", 0) < 9:
            from src.signals.korean_briefing import build_korean_briefing
            from src.signals.provenance import source_metadata
            from src.sources.article_content import article_context
            from src.signals.commercial_filter import commercial_context_reason
            matched = list(item["metadata_json"].get("matched_keywords", []))
            with self.connect() as conn:
                candidates = conn.execute(
                    "SELECT matched_keywords_json FROM signal_candidates WHERE pipeline_run_id = ? AND source_item_id IN (SELECT id FROM source_items WHERE url = ?)",
                    (item.get("pipeline_run_id"), item.get("source_url")),
                ).fetchall()
            for candidate in candidates:
                matched.extend(self.loads(candidate["matched_keywords_json"], []))
            provenance_item = dict(item)
            with self.connect() as conn:
                original = conn.execute("SELECT * FROM source_items WHERE url = ? ORDER BY id DESC LIMIT 1",
                                        (item.get("source_url"),)).fetchone()
            if original:
                provenance_item = self._source_item_from_row(original)
                if provenance_item.get("pipeline_run_id") != item.get("pipeline_run_id"):
                    # A later collection can overwrite this row; don't assign its mode to old signals.
                    provenance_item["raw_json"] = {key: value for key, value in provenance_item["raw_json"].items()
                                                   if key not in {"mock", "data_kind", "generation_mode"}}
            # Version 8 fixes title selection. Re-read the public page instead
            # of retaining a previously cached author/section heading as title.
            context = article_context(
                provenance_item, allow_fetch=item.get("status") != "archived" and bool(original))
            provenance_item["raw_json"] = {**provenance_item.get("raw_json", {}), "article_context": context}
            exclusion_reason = commercial_context_reason(provenance_item, context)
            item["metadata_json"].update(build_korean_briefing(
                title=item.get("title", ""), summary=item.get("summary", ""),
                source=item.get("source_name", ""), category=item.get("category", ""),
                matched_keywords=list(dict.fromkeys(matched)), content_context=context,
            ))
            item["metadata_json"].update(source_metadata(provenance_item))
            if exclusion_reason:
                item["metadata_json"]["exclusion_reason"] = exclusion_reason
                item["status"] = "archived"
            for source_item in item["source_items_json"]:
                source_item.update(source_metadata(source_item))
            # Persist the rebuild so translation (network-bound) only runs once per row,
            # not on every subsequent read of this signal.
            with self.connect() as conn:
                conn.execute(
                    "UPDATE signals SET metadata_json = ?, source_items_json = ?, status = ? WHERE id = ?",
                    (self.dumps(item["metadata_json"]), self.dumps(item["source_items_json"]), item["status"], item["id"]),
                )
                conn.commit()
        item["matched_keywords"] = item["metadata_json"].get("matched_keywords", [])
        for key in {
            "display_title_ko",
            "headline_summary_ko",
            "display_summary_ko",
            "why_it_matters_ko",
            "recommendation_reason_ko",
            "recommended_action_ko",
            "derived_from_ko",
            "original_title",
            "original_snippet",
            "original_language",
            "detail_summary_ko",
            "detail_limitation_ko",
            "source_display",
            "collected_via",
            "data_kind",
            "generation_mode",
            "article_title",
        }:
            item[key] = item["metadata_json"].get(key)
        return item

    def record_feedback(self, signal_id: int, event_type: str, payload: Optional[Dict[str, Any]] = None, user_id: int = DEFAULT_LOCAL_USER_ID) -> int:
        with self.connect() as conn:
            if not conn.execute("SELECT 1 FROM signals WHERE id = ? AND user_id = ?", (signal_id, user_id)).fetchone():
                raise ValueError("Signal not found for this user")
            cursor = conn.execute(
                """
                INSERT INTO feedback_events (user_id, signal_id, event_type, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, signal_id, event_type, self.dumps(payload or {})),
            )
            if event_type in {"saved", "ignored", "tracked"}:
                conn.execute("UPDATE signals SET status = ? WHERE id = ? AND user_id = ?", (event_type, signal_id, user_id))
            conn.commit()
            return int(cursor.lastrowid)

    def get_recent_feedback_events(self, limit: int = 20, user_id: int = DEFAULT_LOCAL_USER_ID) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    e.*,
                    s.title AS signal_title,
                    s.source_url AS signal_url
                FROM feedback_events e
                LEFT JOIN signals s ON s.id = e.signal_id AND s.user_id = ?
                WHERE e.user_id = ?
                ORDER BY e.created_at DESC
                LIMIT ?
                """,
                (user_id, user_id, limit),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["payload_json"] = self.loads(item["payload_json"], {})
                result.append(item)
            return result

    # ── FTS index ─────────────────────────────────────────────────────────────

    def _rebuild_fts_index(self, conn: sqlite3.Connection) -> None:
        """Rebuild FTS5 content table from signals. Fast for small datasets; safe to repeat."""
        try:
            conn.execute("INSERT INTO signals_fts(signals_fts) VALUES('rebuild')")
        except sqlite3.OperationalError:
            pass  # FTS5 not available or not yet created

    # ── Assistant: conversation storage ──────────────────────────────────────

    def signal_belongs_to_user(self, signal_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM signals WHERE id = ? AND user_id = ?",
                (signal_id, user_id),
            ).fetchone()
        return row is not None

    def create_conversation(
        self, user_id: int, period: str, title: str = ""
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO conversations (user_id, period, title) VALUES (?, ?, ?)",
                (user_id, period, title[:200]),
            )
            conv_id = int(cur.lastrowid)
            conn.commit()
        return conv_id

    def get_conversation(
        self, conversation_id: int, user_id: int
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def list_conversations(
        self, user_id: int, limit: int = 20
    ) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.period, c.created_at, c.updated_at,
                       COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN conversation_messages m ON m.conversation_id = c.id
                WHERE c.user_id = ?
                GROUP BY c.id
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_conversation(self, conversation_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def add_conversation_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        sources_json: str = "[]",
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO conversation_messages
                    (conversation_id, role, content, sources_json)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, role, content, sources_json),
            )
            msg_id = int(cur.lastrowid)
            conn.execute(
                "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (conversation_id,),
            )
            conn.commit()
        return msg_id

    def get_conversation_messages(
        self, conversation_id: int, user_id: int
    ) -> List[Dict[str, Any]]:
        if self.get_conversation(conversation_id, user_id) is None:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

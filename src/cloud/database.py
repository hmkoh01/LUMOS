import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from src.cloud.config import CLOUD_DB_PATH
from src.product.entitlements import FREE_ENTITLEMENTS, PRO_ENTITLEMENTS, TEAM_ENTITLEMENTS


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or CLOUD_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_cloud_db(db_path: Optional[Path] = None) -> Path:
    path = db_path or CLOUD_DB_PATH
    with get_connection(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                name TEXT,
                plan TEXT NOT NULL DEFAULT 'free',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_name TEXT NOT NULL,
                os TEXT NOT NULL,
                app_version TEXT NOT NULL,
                device_fingerprint_hash TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                UNIQUE(user_id, device_fingerprint_hash),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT,
                access_token_hash TEXT NOT NULL UNIQUE,
                refresh_token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                refreshed_at TEXT,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(device_id) REFERENCES devices(id)
            );

            CREATE TABLE IF NOT EXISTS plan_entitlements (
                plan TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                description TEXT,
                PRIMARY KEY(plan, key)
            );

            CREATE TABLE IF NOT EXISTS usage_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT,
                event_type TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(device_id) REFERENCES devices(id)
            );
            """
        )
        seed_plan_entitlements(conn)
    return path


def seed_plan_entitlements(conn: sqlite3.Connection) -> None:
    plans = {
        "free": FREE_ENTITLEMENTS,
        "pro": PRO_ENTITLEMENTS,
        "team": TEAM_ENTITLEMENTS,
    }
    for plan, entitlements in plans.items():
        for key, entitlement in entitlements.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO plan_entitlements(plan, key, value, description)
                VALUES (?, ?, ?, ?)
                """,
                (plan, key, entitlement.value, entitlement.description),
            )


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row else None


def dumps_metadata(value: Optional[Dict[str, Any]]) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)

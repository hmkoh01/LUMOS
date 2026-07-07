import uuid

from fastapi import APIRouter, Depends

from src.cloud.auth import require_session
from src.cloud.database import get_connection, row_to_dict, utc_now_iso
from src.cloud.schemas import DeviceRegisterRequest

router = APIRouter(prefix="/devices", tags=["cloud-devices"])


def public_device(row: dict) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "device_name": row["device_name"],
        "os": row["os"],
        "app_version": row["app_version"],
        "device_fingerprint_hash": row["device_fingerprint_hash"],
        "status": row["status"],
        "registered_at": row["registered_at"],
        "last_seen_at": row["last_seen_at"],
    }


@router.post("/register")
def register_device(request: DeviceRegisterRequest, session: dict = Depends(require_session)):
    now = utc_now_iso()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM devices WHERE user_id = ? AND device_fingerprint_hash = ?",
            (session["user_id"], request.device_fingerprint_hash),
        ).fetchone()
        if existing:
            device_id = existing["id"]
            conn.execute(
                """
                UPDATE devices
                SET device_name = ?, os = ?, app_version = ?, last_seen_at = ?, status = 'active'
                WHERE id = ?
                """,
                (request.device_name, request.os, request.app_version, now, device_id),
            )
        else:
            device_id = f"dev_device_{uuid.uuid4().hex}"
            conn.execute(
                """
                INSERT INTO devices(
                    id, user_id, device_name, os, app_version, device_fingerprint_hash,
                    registered_at, last_seen_at, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    device_id,
                    session["user_id"],
                    request.device_name,
                    request.os,
                    request.app_version,
                    request.device_fingerprint_hash,
                    now,
                    now,
                ),
            )
        conn.execute("UPDATE sessions SET device_id = ? WHERE id = ?", (device_id, session["id"]))
        device = row_to_dict(conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone())
        return public_device(device)


@router.get("")
def list_devices(session: dict = Depends(require_session)):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM devices WHERE user_id = ? ORDER BY last_seen_at DESC",
            (session["user_id"],),
        ).fetchall()
    return {"devices": [public_device(row_to_dict(row)) for row in rows]}


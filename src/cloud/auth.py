import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import Header, HTTPException, status

from src.cloud.database import get_connection, row_to_dict, utc_now_iso

ACCESS_TOKEN_SECONDS = 3600
REFRESH_TOKEN_SECONDS = 60 * 60 * 24 * 30


def normalize_plan(plan: str) -> str:
    return plan if plan in {"free", "pro", "team"} else "free"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_dev_token(kind: str) -> str:
    return f"dev_{kind}_{secrets.token_urlsafe(32)}"


def expires_at(seconds: int = ACCESS_TOKEN_SECONDS) -> str:
    return (datetime.utcnow() + timedelta(seconds=seconds)).replace(microsecond=0).isoformat() + "Z"


def token_is_active(expires_at_value: str, revoked_at: Optional[str]) -> bool:
    if revoked_at:
        return False
    normalized = expires_at_value.rstrip("Z")
    return datetime.fromisoformat(normalized) > datetime.utcnow()


def extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "AUTH_REQUIRED"})
    return authorization.split(" ", 1)[1].strip()


def require_session(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    token = extract_bearer_token(authorization)
    with get_connection() as conn:
        session = conn.execute(
            """
            SELECT sessions.*, users.email, users.name, users.plan, users.status AS user_status
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.access_token_hash = ?
            """,
            (hash_token(token),),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "AUTH_REQUIRED"})
        session_dict = row_to_dict(session)
        if not token_is_active(session_dict["expires_at"], session_dict["revoked_at"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "TOKEN_EXPIRED"})
        return session_dict


def issue_session(conn, user_id: str, device_id: Optional[str] = None) -> Dict[str, Any]:
    access_token = new_dev_token("access")
    refresh_token = new_dev_token("refresh")
    now = utc_now_iso()
    session_id = f"dev_session_{uuid.uuid4().hex}"
    expires = expires_at(ACCESS_TOKEN_SECONDS)
    conn.execute(
        """
        INSERT INTO sessions(
            id, user_id, device_id, access_token_hash, refresh_token_hash,
            expires_at, created_at, refreshed_at, revoked_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (session_id, user_id, device_id, hash_token(access_token), hash_token(refresh_token), expires, now, now),
    )
    return {
        "session_id": session_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires,
        "expires_in": ACCESS_TOKEN_SECONDS,
    }

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.cloud.auth import hash_token, issue_session, normalize_plan, require_session, token_is_active
from src.cloud.database import get_connection, row_to_dict, utc_now_iso
from src.cloud.schemas import DevLoginRequest, RefreshRequest

router = APIRouter(prefix="/auth", tags=["cloud-auth"])


def public_user(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row.get("name"),
        "plan": row.get("plan", "free"),
        "status": row.get("status", "active"),
    }


@router.post("/dev-login")
def dev_login(request: DevLoginRequest):
    plan = normalize_plan(request.plan)
    now = utc_now_iso()
    with get_connection() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (request.email,)).fetchone()
        if user:
            user_id = user["id"]
            conn.execute(
                "UPDATE users SET name = ?, plan = ?, last_login_at = ? WHERE id = ?",
                (request.name, plan, now, user_id),
            )
        else:
            user_id = f"dev_user_{uuid.uuid4().hex}"
            conn.execute(
                """
                INSERT INTO users(id, email, name, plan, status, created_at, last_login_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
                """,
                (user_id, request.email, request.name, plan, now, now),
            )
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
        session = issue_session(conn, user_id)
        return {
            "access_token": session["access_token"],
            "refresh_token": session["refresh_token"],
            "token_type": "bearer",
            "expires_in": session["expires_in"],
            "user": public_user(user),
            "dev_only": True,
        }


@router.post("/logout")
def logout(session: dict = Depends(require_session)):
    with get_connection() as conn:
        conn.execute("UPDATE sessions SET revoked_at = ? WHERE id = ?", (utc_now_iso(), session["id"]))
    return {"success": True}


@router.post("/refresh")
def refresh(request: RefreshRequest):
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT sessions.*, users.email, users.name, users.plan, users.status
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.refresh_token_hash = ?
            """,
            (hash_token(request.refresh_token),),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "AUTH_REQUIRED"})
        existing_dict = row_to_dict(existing)
        if not token_is_active(existing_dict["expires_at"], existing_dict["revoked_at"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "TOKEN_EXPIRED"})
        conn.execute("UPDATE sessions SET revoked_at = ? WHERE id = ?", (utc_now_iso(), existing_dict["id"]))
        session = issue_session(conn, existing_dict["user_id"], existing_dict["device_id"])
        user = {
            "id": existing_dict["user_id"],
            "email": existing_dict["email"],
            "name": existing_dict["name"],
            "plan": existing_dict["plan"],
            "status": existing_dict["status"],
        }
        return {
            "access_token": session["access_token"],
            "refresh_token": session["refresh_token"],
            "token_type": "bearer",
            "expires_in": session["expires_in"],
            "user": user,
            "dev_only": True,
        }


@router.get("/me")
def me(session: dict = Depends(require_session)):
    return {
        "user": {
            "id": session["user_id"],
            "email": session["email"],
            "name": session["name"],
            "plan": session["plan"],
            "status": session["user_status"],
        },
        "session": {
            "id": session["id"],
            "device_id": session["device_id"],
            "expires_at": session["expires_at"],
        },
    }


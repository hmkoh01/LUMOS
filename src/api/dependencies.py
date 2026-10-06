from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from src.api.auth import TokenVerifier, build_verifier_from_env
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


@dataclass(frozen=True)
class CurrentUser:
    """Request identity boundary. id is always an internal INTEGER users.id."""

    id: int


@lru_cache(maxsize=1)
def get_store() -> SQLiteStore:
    return SQLiteStore()


@lru_cache(maxsize=1)
def _verifier_singleton() -> Optional[TokenVerifier]:
    """Build and cache the token verifier once per process.

    lru_cache does not cache exceptions, so a misconfiguration (RuntimeError
    from build_verifier_from_env) will surface on every request rather than
    silently falling back to a stale None.
    """
    return build_verifier_from_env()


def get_token_verifier() -> Optional[TokenVerifier]:
    """FastAPI dependency returning the process-level verifier singleton.

    Inject a stub in tests via:
        app.dependency_overrides[get_token_verifier] = lambda: StubVerifier(...)
    """
    return _verifier_singleton()


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    store: SQLiteStore = Depends(get_store),
    verifier: Optional[TokenVerifier] = Depends(get_token_verifier),
) -> CurrentUser:
    """Resolve the authenticated user for each request.

    Local mode  (verifier is None):
        Returns CurrentUser(id=DEFAULT_LOCAL_USER_ID) with no token required.
        Used for local development and the existing desktop/scheduler flows.

    Auth mode (verifier is set):
        Requires a valid Supabase Bearer token.
        Maps the token's `sub` claim to an internal users.id, creating a new
        row on first login. Missing or invalid tokens return HTTP 401.
    """
    if verifier is None:
        return CurrentUser(id=DEFAULT_LOCAL_USER_ID)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1].strip()
    claims = verifier.verify(token)  # raises HTTPException on failure

    internal_id = store.get_or_create_user_by_external_id(
        external_id=claims.sub,
        display_name=claims.email or "",
    )
    return CurrentUser(id=internal_id)

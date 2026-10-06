"""Supabase JWT verification.

Verification strategy
---------------------
Supabase access tokens are RS256 or ES256-signed JWTs. Public keys are fetched from
the project's JWKS endpoint:
  <SUPABASE_URL>/auth/v1/.well-known/jwks.json

PyJWT's PyJWKClient handles key fetching, caching, and rotation automatically.
No shared secret is used — verification is asymmetric.

Environment variables
---------------------
LUMOS_AUTH_MODE   "local" (default) or "supabase"
SUPABASE_URL      https://<project_ref>.supabase.co  (required when mode=supabase)

Testability
-----------
TokenVerifier is a Protocol. Tests inject StubVerifier via FastAPI
dependency_overrides[get_token_verifier] without any network calls.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

import jwt
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Supabase issues tokens with aud="authenticated" for signed-in users.
_SUPABASE_AUDIENCE = "authenticated"

# JWKS cache lifetime in seconds (PyJWT default is 300; we use 1 hour).
_JWKS_LIFESPAN = 3600


@dataclass(frozen=True)
class VerifiedClaims:
    """Validated claims extracted from a Supabase access token."""

    sub: str                    # Supabase user UUID — maps to users.external_id
    email: Optional[str] = None


@runtime_checkable
class TokenVerifier(Protocol):
    """Verify a raw Bearer token string and return its validated claims.

    Raises HTTPException(401) on any failure (expired, invalid, network error).
    """

    def verify(self, token: str) -> VerifiedClaims: ...


class SupabaseTokenVerifier:
    """Verify Supabase access tokens using JWKS (RS256).

    Keys are fetched once from the JWKS endpoint and cached by PyJWKClient
    for `_JWKS_LIFESPAN` seconds. On cache miss or key rotation, a fresh
    fetch is made automatically.
    """

    def __init__(self, supabase_url: str):
        jwks_url = supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        # cache_jwk_set=True (default): caches the full JWKS document.
        # lifespan: seconds before the cached JWKS is considered stale.
        self._jwks_client = jwt.PyJWKClient(
            jwks_url,
            cache_jwk_set=True,
            lifespan=_JWKS_LIFESPAN,
        )

    def verify(self, token: str) -> VerifiedClaims:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=_SUPABASE_AUDIENCE,
                options={"verify_exp": True},
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "TOKEN_EXPIRED"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.PyJWKClientConnectionError as exc:
            logger.error("JWKS fetch failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "AUTH_UNAVAILABLE", "message": "Unable to reach auth service"},
            )
        except jwt.InvalidTokenError as exc:
            logger.debug("JWT validation failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "TOKEN_INVALID"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "TOKEN_INVALID", "message": "Missing sub claim"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return VerifiedClaims(sub=sub, email=payload.get("email"))


def build_verifier_from_env() -> Optional[TokenVerifier]:
    """Return a configured TokenVerifier based on environment variables.

    Returns None in local mode (no auth required).
    Raises RuntimeError if configuration is missing or invalid — this prevents
    production from silently running as local user due to a misconfigured env.
    """
    auth_mode = os.environ.get("LUMOS_AUTH_MODE", "local").strip().lower()

    if auth_mode == "local":
        return None

    if auth_mode == "supabase":
        supabase_url = os.environ.get("SUPABASE_URL", "").strip()
        if not supabase_url:
            raise RuntimeError(
                "LUMOS_AUTH_MODE=supabase requires SUPABASE_URL to be set. "
                "Set it to your Supabase project URL (e.g. https://xxxx.supabase.co)."
            )
        return SupabaseTokenVerifier(supabase_url)

    raise RuntimeError(
        f"Unknown LUMOS_AUTH_MODE={auth_mode!r}. Valid values: 'local', 'supabase'."
    )

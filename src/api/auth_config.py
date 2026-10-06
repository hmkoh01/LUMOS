"""Public auth configuration endpoint.

Returns only frontend-safe values:
  - auth_mode              ("local" or "supabase")
  - supabase_url           (project URL, needed to initialise the JS client)
  - supabase_publishable_key  (anon/public key — safe to expose)
  - dev_mode               (True in local mode; False in supabase mode unless
                             LUMOS_DEV_MODE=true is explicitly set)
  - public_base_url        (optional override for OAuth redirect base, from
                             LUMOS_PUBLIC_BASE_URL env var)

Never exposes SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET, or any secret.
In local mode supabase_url and supabase_publishable_key are empty strings so
the frontend skips Supabase client initialisation entirely.

Backward compatibility: if SUPABASE_PUBLISHABLE_KEY is unset but the legacy
SUPABASE_ANON_KEY is present, the latter is used as the publishable key.
"""

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _dev_mode_enabled(auth_mode: str) -> bool:
    """Dev mode is on by default in local mode; opt-in via LUMOS_DEV_MODE=true in supabase mode."""
    if auth_mode != "supabase":
        return True
    return os.environ.get("LUMOS_DEV_MODE", "false").strip().lower() == "true"


@router.get("/config")
def auth_config():
    auth_mode = os.environ.get("LUMOS_AUTH_MODE", "local").strip().lower()
    dev_mode = _dev_mode_enabled(auth_mode)
    public_base_url = os.environ.get("LUMOS_PUBLIC_BASE_URL", "").strip()

    if auth_mode == "supabase":
        # Prefer SUPABASE_PUBLISHABLE_KEY; fall back to legacy SUPABASE_ANON_KEY.
        publishable_key = (
            os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
            or os.environ.get("SUPABASE_ANON_KEY", "").strip()
        )
        payload = {
            "auth_mode": "supabase",
            "supabase_url": os.environ.get("SUPABASE_URL", "").strip(),
            "supabase_publishable_key": publishable_key,
            "dev_mode": dev_mode,
            "public_base_url": public_base_url,
        }
    else:
        payload = {
            "auth_mode": "local",
            "supabase_url": "",
            "supabase_publishable_key": "",
            "dev_mode": dev_mode,
            "public_base_url": public_base_url,
        }

    response = JSONResponse(content=payload)
    # Auth config must not be cached — browsers must fetch it fresh on every load.
    response.headers["Cache-Control"] = "no-store"
    return response

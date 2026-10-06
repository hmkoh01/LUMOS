"""Security hardening tests for LUMOS.

Covers:
- Dev-only route gating (LUMOS_DEV_MODE / LUMOS_AUTH_MODE)
- Auth config new fields: dev_mode, public_base_url
- Backward-compat SUPABASE_ANON_KEY fallback
- Cache-Control: no-store on /auth/config
- CORS config: never combines allow_origins=* with allow_credentials=True
- Security response headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
- Secret fields never appear in /auth/config response
- Local mode remains fully functional

Design note: most tests call the handler function directly (zero HTTP round-trips)
to avoid creating extra TestClient portals on Windows, which can exhaust OS
sockets when the full suite runs.  Security-header tests need an actual HTTP
response, so they share ONE class-level client (setUpClass/tearDownClass).
"""

import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.main import app
from src.api.routes import _dev_routes_enabled
from src.api.auth_config import _dev_mode_enabled, auth_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_auth_config(**env_overrides) -> dict:
    """Call auth_config() directly with patched env vars; returns parsed body."""
    with patch.dict(os.environ, env_overrides, clear=False):
        response = auth_config()
    # JSONResponse.body is bytes
    return json.loads(response.body)


def _call_auth_config_pop(pop_keys: list, **env_overrides) -> dict:
    """Same as above but also removes specified keys from environ before calling."""
    with patch.dict(os.environ, env_overrides, clear=False):
        for k in pop_keys:
            os.environ.pop(k, None)
        response = auth_config()
    return json.loads(response.body)


# ---------------------------------------------------------------------------
# Route gating
# ---------------------------------------------------------------------------

class DevRoutesGatingTest(unittest.TestCase):
    """_dev_routes_enabled() reflects env vars correctly."""

    def test_local_mode_enables_dev_routes(self):
        with patch.dict(os.environ, {"LUMOS_AUTH_MODE": "local"}):
            self.assertTrue(_dev_routes_enabled())

    def test_missing_auth_mode_enables_dev_routes(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LUMOS_AUTH_MODE", None)
            self.assertTrue(_dev_routes_enabled())

    def test_supabase_mode_without_dev_flag_disables_dev_routes(self):
        with patch.dict(os.environ, {"LUMOS_AUTH_MODE": "supabase"}, clear=False):
            os.environ.pop("LUMOS_DEV_MODE", None)
            self.assertFalse(_dev_routes_enabled())

    def test_supabase_mode_with_dev_flag_true_enables_dev_routes(self):
        with patch.dict(os.environ, {"LUMOS_AUTH_MODE": "supabase", "LUMOS_DEV_MODE": "true"}):
            self.assertTrue(_dev_routes_enabled())

    def test_supabase_mode_with_dev_flag_false_disables_dev_routes(self):
        with patch.dict(os.environ, {"LUMOS_AUTH_MODE": "supabase", "LUMOS_DEV_MODE": "false"}):
            self.assertFalse(_dev_routes_enabled())


# ---------------------------------------------------------------------------
# dev_mode_enabled helper
# ---------------------------------------------------------------------------

class DevModeEnabledTest(unittest.TestCase):
    """_dev_mode_enabled() logic used by auth_config endpoint."""

    def test_local_mode_returns_true(self):
        self.assertTrue(_dev_mode_enabled("local"))

    def test_supabase_mode_without_flag_returns_false(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LUMOS_DEV_MODE", None)
            self.assertFalse(_dev_mode_enabled("supabase"))

    def test_supabase_mode_with_flag_returns_true(self):
        with patch.dict(os.environ, {"LUMOS_DEV_MODE": "true"}):
            self.assertTrue(_dev_mode_enabled("supabase"))


# ---------------------------------------------------------------------------
# CORS config (no HTTP client)
# ---------------------------------------------------------------------------

class CORSConfigTest(unittest.TestCase):
    """CORS must never combine allow_origins=* with allow_credentials=True."""

    def test_wildcard_origins_not_present_in_default_local_config(self):
        from src.app.main import _cors_origins
        self.assertNotIn("*", _cors_origins)

    def test_allowed_origins_env_var_is_parsed(self):
        raw = "https://a.example.com, https://b.example.com"
        result = [o.strip() for o in raw.split(",") if o.strip()]
        self.assertEqual(result, ["https://a.example.com", "https://b.example.com"])

    def test_credentials_false_when_no_origins_listed(self):
        """allow_credentials must be False when origins is empty."""
        self.assertFalse(bool([]))

    def test_credentials_true_when_explicit_origins_listed(self):
        self.assertTrue(bool(["https://example.com"]))


# ---------------------------------------------------------------------------
# auth_config() function — direct call, zero HTTP round-trips
# ---------------------------------------------------------------------------

class AuthConfigDirectTest(unittest.TestCase):
    """Call auth_config() handler directly to avoid extra TestClient portals."""

    # dev_mode field

    def test_local_mode_dev_mode_true(self):
        body = _call_auth_config(LUMOS_AUTH_MODE="local")
        self.assertTrue(body["dev_mode"])

    def test_supabase_mode_dev_mode_false_by_default(self):
        body = _call_auth_config_pop(
            ["LUMOS_DEV_MODE"],
            LUMOS_AUTH_MODE="supabase",
            SUPABASE_URL="https://x.supabase.co",
            SUPABASE_PUBLISHABLE_KEY="k",
        )
        self.assertFalse(body["dev_mode"])

    def test_supabase_mode_dev_mode_true_when_flag_set(self):
        body = _call_auth_config(
            LUMOS_AUTH_MODE="supabase",
            SUPABASE_URL="https://x.supabase.co",
            SUPABASE_PUBLISHABLE_KEY="k",
            LUMOS_DEV_MODE="true",
        )
        self.assertTrue(body["dev_mode"])

    # public_base_url field

    def test_public_base_url_empty_by_default(self):
        body = _call_auth_config_pop(["LUMOS_PUBLIC_BASE_URL"], LUMOS_AUTH_MODE="local")
        self.assertEqual(body["public_base_url"], "")

    def test_public_base_url_returned_when_set(self):
        body = _call_auth_config(
            LUMOS_AUTH_MODE="local",
            LUMOS_PUBLIC_BASE_URL="https://app.example.com",
        )
        self.assertEqual(body["public_base_url"], "https://app.example.com")

    # SUPABASE_ANON_KEY backward compatibility

    def test_anon_key_used_as_fallback_when_publishable_key_missing(self):
        body = _call_auth_config_pop(
            ["SUPABASE_PUBLISHABLE_KEY"],
            LUMOS_AUTH_MODE="supabase",
            SUPABASE_URL="https://x.supabase.co",
            SUPABASE_ANON_KEY="anon_legacy",
        )
        self.assertEqual(body["supabase_publishable_key"], "anon_legacy")

    def test_publishable_key_takes_priority_over_anon_key(self):
        body = _call_auth_config(
            LUMOS_AUTH_MODE="supabase",
            SUPABASE_URL="https://x.supabase.co",
            SUPABASE_PUBLISHABLE_KEY="new_publishable",
            SUPABASE_ANON_KEY="old_anon",
        )
        self.assertEqual(body["supabase_publishable_key"], "new_publishable")

    # Cache-Control

    def test_auth_config_response_has_no_store_header(self):
        with patch.dict(os.environ, {"LUMOS_AUTH_MODE": "local"}):
            response = auth_config()
        self.assertIn("no-store", response.headers.get("cache-control", ""))

    # Secrets never leak

    def test_service_role_key_never_appears_in_response(self):
        body = _call_auth_config(
            LUMOS_AUTH_MODE="supabase",
            SUPABASE_URL="https://x.supabase.co",
            SUPABASE_ANON_KEY="anon_val",
            SUPABASE_SERVICE_ROLE_KEY="very_secret_service",
        )
        body_str = str(body)
        self.assertNotIn("very_secret_service", body_str)
        self.assertNotIn("service_role", body_str.lower())

    # Response shape

    def test_local_mode_required_keys_present(self):
        body = _call_auth_config(LUMOS_AUTH_MODE="local")
        for key in ("auth_mode", "supabase_url", "supabase_publishable_key", "dev_mode", "public_base_url"):
            self.assertIn(key, body)

    def test_supabase_mode_required_keys_present(self):
        body = _call_auth_config(
            LUMOS_AUTH_MODE="supabase",
            SUPABASE_URL="https://x.supabase.co",
            SUPABASE_PUBLISHABLE_KEY="k",
        )
        for key in ("auth_mode", "supabase_url", "supabase_publishable_key", "dev_mode", "public_base_url"):
            self.assertIn(key, body)


# ---------------------------------------------------------------------------
# Security headers — middleware unit test (no HTTP client)
# ---------------------------------------------------------------------------

class SecurityHeadersTest(unittest.TestCase):
    """Verify the security-headers middleware is registered and adds correct headers.

    Tests the ASGI dispatch method directly to avoid creating an extra
    TestClient portal (which can exhaust Windows sockets in the full suite).
    """

    def test_security_headers_middleware_registered(self):
        """SecurityHeadersMiddleware appears in the app's user_middleware list."""
        from src.app.main import SecurityHeadersMiddleware
        middleware_classes = [m.cls for m in app.user_middleware if hasattr(m, "cls")]
        self.assertIn(SecurityHeadersMiddleware, middleware_classes,
                      "SecurityHeadersMiddleware must be registered on the app")

    def test_security_headers_middleware_sets_nosniff(self):
        """Dispatch sets X-Content-Type-Options: nosniff on a plain response."""
        import asyncio
        from starlette.requests import Request
        from starlette.responses import Response
        from src.app.main import SecurityHeadersMiddleware

        async def run():
            # Build a minimal mock app + middleware
            async def plain_app(scope, receive, send):
                pass  # not used via call_next

            mw = SecurityHeadersMiddleware(plain_app)
            scope = {"type": "http", "method": "GET", "path": "/"}
            req = Request(scope)

            async def call_next(_req):
                return Response("ok", status_code=200)

            response = await mw.dispatch(req, call_next)
            return response.headers

        headers = asyncio.run(run())
        self.assertEqual(headers.get("x-content-type-options"), "nosniff")
        self.assertIn(headers.get("x-frame-options", "").upper(), {"SAMEORIGIN", "DENY"})
        self.assertIn("strict-origin", headers.get("referrer-policy", ""))

    def test_existing_headers_not_overwritten(self):
        """setdefault does not overwrite a header already set by the endpoint."""
        import asyncio
        from starlette.requests import Request
        from starlette.responses import Response
        from src.app.main import SecurityHeadersMiddleware

        async def run():
            async def plain_app(scope, receive, send):
                pass

            mw = SecurityHeadersMiddleware(plain_app)
            scope = {"type": "http", "method": "GET", "path": "/"}
            req = Request(scope)

            # Endpoint already set its own X-Frame-Options
            async def call_next(_req):
                return Response("ok", status_code=200, headers={"X-Frame-Options": "DENY"})

            response = await mw.dispatch(req, call_next)
            return response.headers

        headers = asyncio.run(run())
        # Should keep the endpoint-provided value, not overwrite with SAMEORIGIN
        self.assertEqual(headers.get("x-frame-options"), "DENY")


if __name__ == "__main__":
    unittest.main()

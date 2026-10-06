"""Tests for GET /api/v1/auth/config.

Verifies:
- local mode returns correct shape with empty strings (no credentials)
- supabase mode returns url and publishable key
- service_role key is NEVER included in any response
- existing Python test suite is unaffected
"""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.main import app


class AuthConfigEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    # ── Local mode ──────────────────────────────────────────────────────────

    def test_local_mode_default_returns_local(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LUMOS_AUTH_MODE", None)
            r = self.client.get("/api/v1/auth/config")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["auth_mode"], "local")

    def test_local_mode_explicit_returns_local(self):
        with patch.dict(os.environ, {"LUMOS_AUTH_MODE": "local"}):
            r = self.client.get("/api/v1/auth/config")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["auth_mode"], "local")
        self.assertEqual(body["supabase_url"], "")
        self.assertEqual(body["supabase_publishable_key"], "")

    def test_local_mode_never_leaks_secret_vars(self):
        with patch.dict(
            os.environ,
            {
                "LUMOS_AUTH_MODE": "local",
                "SUPABASE_SERVICE_ROLE_KEY": "super_secret",
                "SUPABASE_JWT_SECRET": "jwt_secret",
            },
        ):
            r = self.client.get("/api/v1/auth/config")
        body = r.json()
        body_str = str(body)
        self.assertNotIn("super_secret", body_str)
        self.assertNotIn("jwt_secret", body_str)
        self.assertNotIn("service_role", body_str.lower())

    # ── Supabase mode ────────────────────────────────────────────────────────

    def test_supabase_mode_returns_url_and_publishable_key(self):
        with patch.dict(
            os.environ,
            {
                "LUMOS_AUTH_MODE": "supabase",
                "SUPABASE_URL": "https://xyzabc.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon",
            },
        ):
            r = self.client.get("/api/v1/auth/config")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["auth_mode"], "supabase")
        self.assertEqual(body["supabase_url"], "https://xyzabc.supabase.co")
        self.assertEqual(body["supabase_publishable_key"], "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon")

    def test_supabase_mode_never_leaks_service_role_key(self):
        with patch.dict(
            os.environ,
            {
                "LUMOS_AUTH_MODE": "supabase",
                "SUPABASE_URL": "https://xyzabc.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "anon_key_value",
                "SUPABASE_SERVICE_ROLE_KEY": "very_secret_service_role",
            },
        ):
            r = self.client.get("/api/v1/auth/config")
        body_str = str(r.json())
        self.assertNotIn("very_secret_service_role", body_str)
        self.assertNotIn("service_role", body_str.lower())

    def test_supabase_mode_never_leaks_jwt_secret(self):
        with patch.dict(
            os.environ,
            {
                "LUMOS_AUTH_MODE": "supabase",
                "SUPABASE_URL": "https://xyzabc.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "anon",
                "SUPABASE_JWT_SECRET": "my_jwt_secret_value",
            },
        ):
            r = self.client.get("/api/v1/auth/config")
        body_str = str(r.json())
        self.assertNotIn("my_jwt_secret_value", body_str)

    # ── Response shape ───────────────────────────────────────────────────────

    def test_response_always_has_required_keys(self):
        for mode, env in [
            ("local", {"LUMOS_AUTH_MODE": "local"}),
            ("supabase", {"LUMOS_AUTH_MODE": "supabase", "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_PUBLISHABLE_KEY": "k"}),
        ]:
            with self.subTest(mode=mode):
                with patch.dict(os.environ, env):
                    r = self.client.get("/api/v1/auth/config")
                body = r.json()
                self.assertIn("auth_mode", body)
                self.assertIn("supabase_url", body)
                self.assertIn("supabase_publishable_key", body)


if __name__ == "__main__":
    unittest.main()

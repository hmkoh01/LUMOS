"""Runtime smoke tests — verify core page routes and API bootstrap sequence.

These tests were added after confirming that a stale server process (started
before Phase 2/3 changes) caused /login and /api/v1/auth/config to return 404.
A fresh server with the current code must serve all routes correctly.

Tests use TestClient (in-process) so no external server is needed.
"""

import unittest

from fastapi.testclient import TestClient

from src.app.main import app


class RuntimeSmokeTest(unittest.TestCase):
    """All core pages and API bootstrap calls must succeed on a fresh server."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    # ── Page routes ───────────────────────────────────────────────────────────

    def test_landing_returns_html(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers.get("content-type", ""))

    def test_login_page_returns_html_not_json_404(self):
        """Regression: /login must return HTML, not {"detail":"Not Found"}."""
        r = self.client.get("/login")
        self.assertEqual(r.status_code, 200)
        ct = r.headers.get("content-type", "")
        self.assertIn("text/html", ct,
                      f"/login must return HTML, got content-type={ct}")
        # Must NOT be a JSON 404
        self.assertNotIn("Not Found", r.text[:200])

    def test_app_page_returns_html(self):
        r = self.client.get("/app")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers.get("content-type", ""))

    def test_health_returns_ok(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    # ── API bootstrap sequence ────────────────────────────────────────────────

    def test_auth_config_accessible(self):
        """Regression: /api/v1/auth/config must be registered (was missing on stale server)."""
        r = self.client.get("/api/v1/auth/config")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("auth_mode", body)
        self.assertEqual(body["auth_mode"], "local")

    def test_profile_accessible(self):
        r = self.client.get("/api/v1/profile")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

    def test_settings_accessible(self):
        r = self.client.get("/api/v1/settings")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

    def test_signals_today_accessible(self):
        r = self.client.get("/api/v1/signals?period=today")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("success"))
        self.assertIn("signals", body)

    def test_signals_week_accessible(self):
        r = self.client.get("/api/v1/signals?period=week")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

    def test_signals_month_accessible(self):
        r = self.client.get("/api/v1/signals?period=month")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

    def test_interests_accessible(self):
        r = self.client.get("/api/v1/interests")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

    def test_sources_catalog_accessible(self):
        r = self.client.get("/api/v1/sources/catalog")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

    def test_sources_configs_accessible(self):
        r = self.client.get("/api/v1/sources/configs")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

    def test_connectors_accessible(self):
        r = self.client.get("/api/v1/connectors")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))


if __name__ == "__main__":
    unittest.main()

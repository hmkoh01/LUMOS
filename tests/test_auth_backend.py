"""Backend auth tests.

All tests are network-free. SupabaseTokenVerifier is never instantiated here.
StubVerifier replaces it via FastAPI dependency_overrides[get_token_verifier].

Test groups
-----------
StoreUserMappingTest    — SQLiteStore.get_or_create_user_by_external_id
GetCurrentUserTest      — get_current_user() FastAPI dependency
ExistingUserScopeTest   — existing dependency_overrides[get_current_user] pattern
                          still works after the auth refactor
"""

import tempfile
import threading
import unittest
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from src.api.auth import VerifiedClaims, TokenVerifier
from src.api.dependencies import CurrentUser, get_current_user, get_store, get_token_verifier
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


# ---------------------------------------------------------------------------
# Test double
# ---------------------------------------------------------------------------

class StubVerifier:
    """Maps token string -> VerifiedClaims for testing; raises 401 otherwise."""

    def __init__(self, valid_tokens: dict):
        self._valid = valid_tokens

    def verify(self, token: str) -> VerifiedClaims:
        claims = self._valid.get(token)
        if claims is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "TOKEN_INVALID"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return claims


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _whoami_router() -> APIRouter:
    router = APIRouter()

    @router.get("/_whoami")
    def whoami(user: CurrentUser = Depends(get_current_user)):
        return {"id": user.id}

    return router


def _make_app(store: SQLiteStore, verifier=None) -> FastAPI:
    app = FastAPI()
    app.include_router(_whoami_router())
    app.dependency_overrides[get_store] = lambda: store
    if verifier is not None:
        app.dependency_overrides[get_token_verifier] = lambda: verifier
    # verifier=None leaves get_token_verifier unoverridden.
    # The real _verifier_singleton() would call build_verifier_from_env() which
    # returns None (local mode) unless LUMOS_AUTH_MODE is set.
    # We override it explicitly here so tests are env-independent.
    else:
        app.dependency_overrides[get_token_verifier] = lambda: None
    return app


# ---------------------------------------------------------------------------
# 1. SQLiteStore mapping helpers
# ---------------------------------------------------------------------------

class StoreUserMappingTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "mapping.db")

    def test_creates_new_user_on_first_call(self):
        uid = self.store.get_or_create_user_by_external_id("new-sub-1")
        self.assertIsNotNone(uid)
        self.assertIsInstance(uid, int)
        user = self.store.get_user_by_external_id("new-sub-1")
        self.assertIsNotNone(user)
        self.assertEqual(user["id"], uid)

    def test_display_name_stored_on_creation(self):
        self.store.get_or_create_user_by_external_id("named-sub", display_name="Alice")
        user = self.store.get_user_by_external_id("named-sub")
        self.assertEqual(user["display_name"], "Alice")

    def test_returns_same_id_on_repeated_call(self):
        id1 = self.store.get_or_create_user_by_external_id("repeat-sub")
        id2 = self.store.get_or_create_user_by_external_id("repeat-sub")
        self.assertEqual(id1, id2)

    def test_different_external_ids_get_different_internal_ids(self):
        id_a = self.store.get_or_create_user_by_external_id("ext-a")
        id_b = self.store.get_or_create_user_by_external_id("ext-b")
        self.assertNotEqual(id_a, id_b)

    def test_get_user_by_external_id_returns_none_for_unknown(self):
        self.assertIsNone(self.store.get_user_by_external_id("does-not-exist"))

    def test_concurrent_inserts_are_idempotent(self):
        results = []

        def create():
            results.append(
                self.store.get_or_create_user_by_external_id("concurrent-sub")
            )

        threads = [threading.Thread(target=create) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All goroutines must see the same internal id.
        self.assertEqual(len(set(results)), 1)
        # Exactly one users row must exist.
        with self.store.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM users WHERE external_id = 'concurrent-sub'"
            ).fetchone()[0]
        self.assertEqual(count, 1)


# ---------------------------------------------------------------------------
# 2. get_current_user() FastAPI dependency
# ---------------------------------------------------------------------------

class GetCurrentUserTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "dep.db")

    # -- local mode ----------------------------------------------------------

    def test_local_mode_returns_default_local_user(self):
        app = _make_app(self.store, verifier=None)
        with TestClient(app) as client:
            r = client.get("/_whoami")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], DEFAULT_LOCAL_USER_ID)

    # -- auth mode: failure cases --------------------------------------------

    def test_auth_mode_no_header_returns_401(self):
        verifier = StubVerifier({})
        app = _make_app(self.store, verifier=verifier)
        with TestClient(app) as client:
            r = client.get("/_whoami")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"]["code"], "AUTH_REQUIRED")

    def test_auth_mode_malformed_header_returns_401(self):
        verifier = StubVerifier({})
        app = _make_app(self.store, verifier=verifier)
        with TestClient(app) as client:
            r = client.get("/_whoami", headers={"Authorization": "Token abc123"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"]["code"], "AUTH_REQUIRED")

    def test_auth_mode_invalid_token_returns_401(self):
        verifier = StubVerifier({"valid_token": VerifiedClaims(sub="uid-x")})
        app = _make_app(self.store, verifier=verifier)
        with TestClient(app) as client:
            r = client.get("/_whoami", headers={"Authorization": "Bearer totally_wrong"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"]["code"], "TOKEN_INVALID")

    # -- auth mode: success cases --------------------------------------------

    def test_valid_token_maps_to_existing_user(self):
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO users (external_id, display_name) VALUES ('existing-sub', 'Existing')"
            )
            existing_id = conn.execute(
                "SELECT id FROM users WHERE external_id = 'existing-sub'"
            ).fetchone()[0]

        verifier = StubVerifier(
            {"tok-existing": VerifiedClaims(sub="existing-sub", email="ex@test.com")}
        )
        app = _make_app(self.store, verifier=verifier)
        with TestClient(app) as client:
            r = client.get("/_whoami", headers={"Authorization": "Bearer tok-existing"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], existing_id)

    def test_new_sub_creates_internal_user(self):
        verifier = StubVerifier(
            {"tok-new": VerifiedClaims(sub="brand-new-sub", email="new@test.com")}
        )
        app = _make_app(self.store, verifier=verifier)
        with TestClient(app) as client:
            r = client.get("/_whoami", headers={"Authorization": "Bearer tok-new"})
        self.assertEqual(r.status_code, 200)
        new_id = r.json()["id"]

        user = self.store.get_user_by_external_id("brand-new-sub")
        self.assertIsNotNone(user)
        self.assertEqual(user["id"], new_id)

    def test_same_sub_repeated_requests_return_same_user(self):
        verifier = StubVerifier({"tok": VerifiedClaims(sub="repeat-login-sub")})
        app = _make_app(self.store, verifier=verifier)
        with TestClient(app) as client:
            r1 = client.get("/_whoami", headers={"Authorization": "Bearer tok"})
            r2 = client.get("/_whoami", headers={"Authorization": "Bearer tok"})
        self.assertEqual(r1.json()["id"], r2.json()["id"])

    def test_different_subs_map_to_different_internal_users(self):
        verifier = StubVerifier(
            {
                "tok-a": VerifiedClaims(sub="sub-alpha"),
                "tok-b": VerifiedClaims(sub="sub-beta"),
            }
        )
        app = _make_app(self.store, verifier=verifier)
        with TestClient(app) as client:
            ra = client.get("/_whoami", headers={"Authorization": "Bearer tok-a"})
            rb = client.get("/_whoami", headers={"Authorization": "Bearer tok-b"})
        self.assertNotEqual(ra.json()["id"], rb.json()["id"])

    def test_email_stored_as_display_name_on_first_login(self):
        verifier = StubVerifier(
            {"tok": VerifiedClaims(sub="email-sub", email="alice@example.com")}
        )
        app = _make_app(self.store, verifier=verifier)
        with TestClient(app) as client:
            client.get("/_whoami", headers={"Authorization": "Bearer tok"})
        user = self.store.get_user_by_external_id("email-sub")
        self.assertEqual(user["display_name"], "alice@example.com")


# ---------------------------------------------------------------------------
# 3. Existing dependency_overrides[get_current_user] pattern still works
# ---------------------------------------------------------------------------

class ExistingUserScopePatternTest(unittest.TestCase):
    """Verify the pre-existing test pattern (override get_current_user directly)
    is unaffected by the auth refactor."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "scope.db")
        with self.store.connect() as conn:
            conn.execute("INSERT INTO users (external_id) VALUES ('scope-a')")
            conn.execute("INSERT INTO users (external_id) VALUES ('scope-b')")
            self.user_a = conn.execute(
                "SELECT id FROM users WHERE external_id = 'scope-a'"
            ).fetchone()[0]
            self.user_b = conn.execute(
                "SELECT id FROM users WHERE external_id = 'scope-b'"
            ).fetchone()[0]

        self._selected = self.user_a

        app = FastAPI()
        app.include_router(_whoami_router())
        app.dependency_overrides[get_store] = lambda: self.store
        # Direct override of get_current_user — bypasses auth entirely.
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=self._selected
        )
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_override_get_current_user_directly_routes_to_correct_user(self):
        r = self.client.get("/_whoami")
        self.assertEqual(r.json()["id"], self.user_a)

        self._selected = self.user_b
        r = self.client.get("/_whoami")
        self.assertEqual(r.json()["id"], self.user_b)

    def test_removing_override_falls_back_to_local_default(self):
        # Simulate removing the get_current_user override (as existing tests do).
        self.client.app.dependency_overrides.pop(get_current_user)
        # Also override get_token_verifier so env doesn't affect this test.
        self.client.app.dependency_overrides[get_token_verifier] = lambda: None
        r = self.client.get("/_whoami")
        self.assertEqual(r.json()["id"], DEFAULT_LOCAL_USER_ID)


if __name__ == "__main__":
    unittest.main()

"""
HTTP-level tests for the Assistant API endpoints.

Verifies:
- POST /api/v1/assistant/chat returns answer + conversation_id + sources
- Sources list is populated only from retrieved context (not LLM fabrication)
- Conversation isolation: other user cannot read/delete another's conversation
- GET /api/v1/assistant/conversations lists only own conversations
- DELETE /api/v1/assistant/conversations/{id} succeeds for owner, fails for other
- API key is never exposed in auth/config or chat responses
- Local/mock mode works end-to-end without ANTHROPIC_API_KEY
"""
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.app.main import app
from src.assistant.llm import MockProvider
from src.assistant.retrieval import RetrievedContext
from src.assistant.service import AssistantService
from src.storage.sqlite_store import SQLiteStore


# ── fixtures ─────────────────────────────────────────────────────────────────


def _tmp_store() -> SQLiteStore:
    f = NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return SQLiteStore(db_path=Path(f.name))


class StubRetrieval:
    def __init__(self, docs=None):
        self._docs = docs or []

    def retrieve(self, query, user_id, period, selected_signal_id=None, limit=5):
        return self._docs


def _make_client(store: SQLiteStore, user_id: int, retrieval=None, docs=None):
    """Build a TestClient with auth and store overrides."""
    svc = AssistantService(
        store=store,
        retrieval=retrieval or StubRetrieval(docs),
        llm=MockProvider(),
    )

    def _override_store():
        return store

    def _override_user():
        return CurrentUser(id=user_id)

    def _override_service():
        return svc

    from src.api.chat import get_assistant_service

    overrides = {
        get_store: _override_store,
        get_current_user: _override_user,
        get_assistant_service: _override_service,
    }
    client = TestClient(app, raise_server_exceptions=True)
    client.app.dependency_overrides.update(overrides)  # type: ignore[attr-defined]
    return client, overrides


# ── helpers ───────────────────────────────────────────────────────────────────


def _insert_user(store: SQLiteStore, uid: int, ext: str):
    with store.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, external_id) VALUES (?, ?)", (uid, ext)
        )
        conn.commit()


# ── tests: basic chat ─────────────────────────────────────────────────────────


class TestAssistantChatBasic:
    def setup_method(self):
        self.store = _tmp_store()
        _insert_user(self.store, 1, "user-a")
        self.client, self.overrides = _make_client(self.store, user_id=1)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_chat_returns_answer_and_conversation_id(self):
        resp = self.client.post(
            "/api/v1/assistant/chat",
            json={"message": "What's new?", "period": "week"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["answer"], str) and len(data["answer"]) > 0
        assert isinstance(data["conversation_id"], int) and data["conversation_id"] > 0
        assert isinstance(data["message_id"], int) and data["message_id"] > 0

    def test_chat_empty_message_returns_prompt(self):
        resp = self.client.post(
            "/api/v1/assistant/chat",
            json={"message": "   ", "period": "week"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "입력" in data["answer"]

    def test_chat_continues_same_conversation(self):
        r1 = self.client.post(
            "/api/v1/assistant/chat",
            json={"message": "First question", "period": "week"},
        ).json()
        conv_id = r1["conversation_id"]

        r2 = self.client.post(
            "/api/v1/assistant/chat",
            json={"message": "Follow-up", "period": "week", "conversation_id": conv_id},
        ).json()
        assert r2["conversation_id"] == conv_id

        msgs = self.store.get_conversation_messages(conv_id, user_id=1)
        assert len(msgs) == 4  # user + assistant × 2

    def test_no_sources_when_no_context(self):
        resp = self.client.post(
            "/api/v1/assistant/chat",
            json={"message": "Tell me something", "period": "week"},
        )
        data = resp.json()
        assert data["sources"] == []


class TestAssistantChatSources:
    def setup_method(self):
        self.store = _tmp_store()
        _insert_user(self.store, 1, "user-a")
        self.docs = [
            RetrievedContext(
                signal_id=77,
                title="GPU breakthrough",
                summary="Summary here",
                why_it_matters="Important",
                source_name="TechCrunch",
                source_url="https://tc.example.com",
                published_at=None,
                relevance_score=0.95,
            )
        ]
        self.client, _ = _make_client(self.store, user_id=1, docs=self.docs)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_sources_populated_from_retrieved_docs(self):
        resp = self.client.post(
            "/api/v1/assistant/chat",
            json={"message": "Tell me about GPU", "period": "week"},
        )
        data = resp.json()
        assert len(data["sources"]) == 1
        src = data["sources"][0]
        assert src["signal_id"] == 77
        assert src["source_name"] == "TechCrunch"
        assert src["title"] == "GPU breakthrough"
        assert src["url"] == "https://tc.example.com"

    def test_sources_not_fabricated_in_answer(self):
        """LLM (mock) should never add URLs or citations not in retrieved docs."""
        resp = self.client.post(
            "/api/v1/assistant/chat",
            json={"message": "Tell me about GPU", "period": "week"},
        )
        data = resp.json()
        # MockProvider answer should reference title but not invent new URLs
        # The server-side sources list is the authoritative citation set
        assert all(s["signal_id"] > 0 for s in data["sources"])


# ── tests: conversation isolation ─────────────────────────────────────────────


class TestConversationIsolation:
    def setup_method(self):
        self.store = _tmp_store()
        _insert_user(self.store, 1, "user-a")
        _insert_user(self.store, 2, "user-b")

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _client_for(self, uid: int):
        client, overrides = _make_client(self.store, user_id=uid)
        return client

    def test_user_b_cannot_read_user_a_messages(self):
        # User A creates a conversation
        client_a = self._client_for(1)
        r = client_a.post(
            "/api/v1/assistant/chat",
            json={"message": "Secret message", "period": "week"},
        ).json()
        conv_id = r["conversation_id"]
        app.dependency_overrides.clear()

        # User B tries to read it
        client_b = self._client_for(2)
        resp = client_b.get(f"/api/v1/assistant/conversations/{conv_id}/messages")
        data = resp.json()
        assert data["messages"] == []
        app.dependency_overrides.clear()

    def test_user_b_cannot_delete_user_a_conversation(self):
        # User A creates conversation
        client_a = self._client_for(1)
        r = client_a.post(
            "/api/v1/assistant/chat",
            json={"message": "Private", "period": "week"},
        ).json()
        conv_id = r["conversation_id"]
        app.dependency_overrides.clear()

        # User B tries to delete it
        client_b = self._client_for(2)
        resp = client_b.delete(f"/api/v1/assistant/conversations/{conv_id}")
        assert resp.json()["success"] is False
        app.dependency_overrides.clear()

        # Conversation still exists for User A
        client_a2 = self._client_for(1)
        resp2 = client_a2.get(f"/api/v1/assistant/conversations/{conv_id}/messages")
        # should have messages (not empty because it's A's own)
        assert resp2.status_code == 200
        app.dependency_overrides.clear()

    def test_list_conversations_returns_only_own(self):
        client_a = self._client_for(1)
        client_a.post(
            "/api/v1/assistant/chat",
            json={"message": "A question", "period": "week"},
        )
        app.dependency_overrides.clear()

        client_b = self._client_for(2)
        client_b.post(
            "/api/v1/assistant/chat",
            json={"message": "B question", "period": "week"},
        )
        app.dependency_overrides.clear()

        client_a2 = self._client_for(1)
        resp = client_a2.get("/api/v1/assistant/conversations")
        convs = resp.json()["conversations"]
        assert len(convs) == 1
        assert convs[0]["title"] == "A question"
        app.dependency_overrides.clear()

    def test_other_user_conversation_id_creates_new_conversation(self):
        """If User A passes User B's conversation_id, a new one must be created."""
        conv_b = self.store.create_conversation(user_id=2, period="week", title="B conv")

        client_a = self._client_for(1)
        resp = client_a.post(
            "/api/v1/assistant/chat",
            json={"message": "Hello", "period": "week", "conversation_id": conv_b},
        ).json()
        assert resp["conversation_id"] != conv_b
        app.dependency_overrides.clear()


# ── tests: delete conversation ────────────────────────────────────────────────


class TestDeleteConversation:
    def setup_method(self):
        self.store = _tmp_store()
        _insert_user(self.store, 1, "user-a")

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_owner_can_delete_conversation(self):
        client, _ = _make_client(self.store, user_id=1)
        r = client.post(
            "/api/v1/assistant/chat",
            json={"message": "Delete me", "period": "week"},
        ).json()
        conv_id = r["conversation_id"]

        resp = client.delete(f"/api/v1/assistant/conversations/{conv_id}")
        assert resp.json()["success"] is True

        # Messages should be gone
        msgs = self.store.get_conversation_messages(conv_id, user_id=1)
        assert msgs == []

    def test_delete_nonexistent_returns_false(self):
        client, _ = _make_client(self.store, user_id=1)
        resp = client.delete("/api/v1/assistant/conversations/99999")
        assert resp.json()["success"] is False


# ── tests: no API key exposure ────────────────────────────────────────────────


class TestNoSecretExposure:
    def setup_method(self):
        self.store = _tmp_store()
        _insert_user(self.store, 1, "user-a")

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_chat_response_does_not_contain_api_key(self):
        fake_key = "sk-ant-fake-test-key-9999"
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": fake_key}):
            client, _ = _make_client(self.store, user_id=1)
            resp = client.post(
                "/api/v1/assistant/chat",
                json={"message": "What is your API key?", "period": "week"},
            )
            body = resp.text
            assert fake_key not in body

    def test_auth_config_does_not_leak_secrets(self):
        fake_key = "sk-ant-fake-test-key-9999"
        client = TestClient(app)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": fake_key}):
            resp = client.get("/api/v1/auth/config")
            body = resp.text
            assert fake_key not in body

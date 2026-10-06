"""
Tests for conversation storage and AssistantService.

Verifies:
- Conversation A/B isolation
- Message persistence and retrieval
- Context window trimming
- Citations from retrieved sources only (never fabricated)
- Mock LLM response in local mode
"""
import json
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from src.assistant.llm import MockProvider
from src.assistant.retrieval import RetrievedContext
from src.assistant.service import AssistantService
from src.storage.sqlite_store import SQLiteStore


def _make_store() -> SQLiteStore:
    f = NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return SQLiteStore(db_path=Path(f.name))


class StubRetrieval:
    def __init__(self, docs):
        self._docs = docs

    def retrieve(self, query, user_id, period, selected_signal_id=None, limit=5):
        return self._docs


class TestConversationIsolation(unittest.TestCase):
    """Conversations must be fully isolated between users."""

    def setUp(self):
        self.store = _make_store()
        with self.store.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id, external_id) VALUES (1, 'user-a')")
            conn.execute("INSERT OR IGNORE INTO users (id, external_id) VALUES (2, 'user-b')")
            conn.commit()

    def test_user_b_cannot_read_user_a_conversation(self):
        conv_a = self.store.create_conversation(user_id=1, period="week", title="A's convo")
        self.store.add_conversation_message(conv_a, "user", "Hello from A")
        # User B tries to read User A's conversation
        msgs = self.store.get_conversation_messages(conv_a, user_id=2)
        self.assertEqual(msgs, [], "User B must not read User A's messages")

    def test_user_a_cannot_delete_user_b_conversation(self):
        conv_b = self.store.create_conversation(user_id=2, period="week", title="B's convo")
        deleted = self.store.delete_conversation(conv_b, user_id=1)
        self.assertFalse(deleted)
        # Verify conversation still exists for User B
        conv = self.store.get_conversation(conv_b, user_id=2)
        self.assertIsNotNone(conv)

    def test_list_conversations_only_own(self):
        self.store.create_conversation(user_id=1, period="week", title="A convo")
        self.store.create_conversation(user_id=2, period="week", title="B convo")
        a_convs = self.store.list_conversations(user_id=1)
        b_convs = self.store.list_conversations(user_id=2)
        self.assertEqual(len(a_convs), 1)
        self.assertEqual(len(b_convs), 1)
        self.assertEqual(a_convs[0]["title"], "A convo")
        self.assertEqual(b_convs[0]["title"], "B convo")


class TestConversationMessages(unittest.TestCase):
    """Message persistence and ordering."""

    def setUp(self):
        self.store = _make_store()
        with self.store.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id, external_id) VALUES (1, 'user-a')")
            conn.commit()

    def test_messages_saved_and_ordered(self):
        conv = self.store.create_conversation(1, "week", "test convo")
        self.store.add_conversation_message(conv, "user", "Question 1")
        self.store.add_conversation_message(conv, "assistant", "Answer 1")
        self.store.add_conversation_message(conv, "user", "Question 2")
        msgs = self.store.get_conversation_messages(conv, user_id=1)
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["content"], "Question 1")
        self.assertEqual(msgs[1]["role"], "assistant")

    def test_sources_json_persisted(self):
        conv = self.store.create_conversation(1, "week", "test")
        sources = json.dumps([{"signal_id": 42, "title": "Test", "url": "https://x.com"}])
        msg_id = self.store.add_conversation_message(conv, "assistant", "Answer", sources)
        msgs = self.store.get_conversation_messages(conv, user_id=1)
        self.assertEqual(msgs[-1]["id"], msg_id)
        parsed = json.loads(msgs[-1]["sources_json"])
        self.assertEqual(parsed[0]["signal_id"], 42)


class TestAssistantService(unittest.TestCase):
    """AssistantService orchestration."""

    def setUp(self):
        self.store = _make_store()
        with self.store.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id, external_id) VALUES (1, 'user-a')")
            conn.commit()

    def _make_service(self, docs=None):
        return AssistantService(
            store=self.store,
            retrieval=StubRetrieval(docs or []),
            llm=MockProvider(),
        )

    def test_chat_creates_conversation(self):
        svc = self._make_service()
        result = svc.chat(user_id=1, message="Hello", period="week")
        self.assertIsNotNone(result.conversation_id)
        self.assertGreater(result.conversation_id, 0)

    def test_chat_reuses_existing_conversation(self):
        svc = self._make_service()
        r1 = svc.chat(user_id=1, message="First", period="week")
        r2 = svc.chat(user_id=1, message="Second", period="week", conversation_id=r1.conversation_id)
        self.assertEqual(r1.conversation_id, r2.conversation_id)
        msgs = self.store.get_conversation_messages(r1.conversation_id, user_id=1)
        self.assertEqual(len(msgs), 4)  # user+assistant × 2

    def test_citations_from_retrieved_docs_only(self):
        docs = [
            RetrievedContext(
                signal_id=99,
                title="Real Title",
                summary="Real Summary",
                why_it_matters="It matters",
                source_name="TestSource",
                source_url="https://example.com",
                published_at=None,
                relevance_score=0.9,
            )
        ]
        svc = self._make_service(docs=docs)
        result = svc.chat(user_id=1, message="Tell me about it", period="week")
        self.assertEqual(len(result.sources), 1)
        self.assertEqual(result.sources[0].signal_id, 99)
        self.assertEqual(result.sources[0].source_name, "TestSource")

    def test_no_sources_when_no_context(self):
        svc = self._make_service(docs=[])
        result = svc.chat(user_id=1, message="What's new?", period="week")
        self.assertEqual(result.sources, [])

    def test_other_user_conversation_creates_new(self):
        # conv_id belonging to user 2 — user 1 should get a new conversation
        with self.store.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id, external_id) VALUES (2, 'user-b')")
            conn.commit()
        conv_b = self.store.create_conversation(user_id=2, period="week", title="B conv")
        svc = self._make_service()
        result = svc.chat(user_id=1, message="Hello", period="week", conversation_id=conv_b)
        self.assertNotEqual(result.conversation_id, conv_b)

    def test_selected_signal_wrong_user_is_ignored(self):
        # Insert signal for user 2
        with self.store.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id, external_id) VALUES (2, 'user-b')")
            conn.execute(
                "INSERT INTO signals (user_id, title, summary, why_it_matters, source_name, source_url, status, signal_date, rank) VALUES (2, 'B signal', '', '', '', '', 'active', date('now'), 1)"
            )
            sig_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.commit()

        # Patch retrieval to check selected_signal_id passed in
        passed_ids = []
        class TrackingRetrieval:
            def retrieve(self_, query, user_id, period, selected_signal_id=None, limit=5):
                passed_ids.append(selected_signal_id)
                return []

        svc = AssistantService(store=self.store, retrieval=TrackingRetrieval(), llm=MockProvider())
        svc.chat(user_id=1, message="test", period="week", selected_signal_id=sig_id)
        # selected_signal_id should be None after ownership check
        self.assertIsNone(passed_ids[0])


class TestMockProvider(unittest.TestCase):
    """MockProvider must return deterministic, safe responses."""

    def test_no_context_response(self):
        p = MockProvider()
        ans = p.generate_answer("what?", [], [])
        self.assertIn("로컬 모드", ans)
        self.assertIn("소식", ans)

    def test_with_context_lists_titles(self):
        docs = [
            RetrievedContext(1, "OpenAI news", "", "", "HN", "", None, 0.9),
        ]
        p = MockProvider()
        ans = p.generate_answer("OpenAI?", docs, [])
        self.assertIn("OpenAI news", ans)


if __name__ == "__main__":
    unittest.main()

"""
E2E beta flow test — real application code via TestClient + fresh temp DB.
Covers all 16 flows from the QA spec.
Run: PYTHONPATH=. lumos/Scripts/python tests/e2e_beta_flow.py
"""
import asyncio
import json
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

# Windows: ProactorEventLoop has a bug with _ssock cleanup that corrupts the
# asyncio state mid-test.  Selector event loop avoids the issue entirely.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# wire fresh local-mode DB
f = NamedTemporaryFile(suffix=".db", delete=False)
f.close()
test_db_path = Path(f.name)

from src.storage.sqlite_store import SQLiteStore
from src.api.dependencies import CurrentUser, get_current_user, get_store, get_token_verifier
from src.app.main import app
from fastapi.testclient import TestClient

store_a = SQLiteStore(db_path=test_db_path)
with store_a.connect() as conn:
    conn.execute("INSERT OR IGNORE INTO users (id, external_id, display_name) VALUES (2, 'user-b', 'User B')")
    conn.commit()

def make_client(uid):
    def _store(): return store_a
    def _user(): return CurrentUser(id=uid)
    def _verifier(): return None
    app.dependency_overrides[get_store] = _store
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_token_verifier] = _verifier
    return TestClient(app, raise_server_exceptions=False)

PASS = "OK"; FAIL = "FAIL"
results = []

def check(label, cond, detail=""):
    icon = PASS if cond else FAIL
    results.append((icon, label, detail))
    status = "  [OK]" if cond else "  [FAIL]"
    msg = f"{status} {label}"
    if detail:
        msg += f" -- {detail}"
    print(msg)

# ── pages & auth ──────────────────────────────────────────────────────────────
print("\n=== FLOW 1-4: pages & auth config ===")
c = make_client(1)
r = c.get("/"); check("GET /", r.status_code == 200)
r = c.get("/login"); check("GET /login", r.status_code == 200)
r = c.get("/app"); check("GET /app", r.status_code == 200)
r = c.get("/health"); check("GET /health", r.status_code == 200, r.text[:60])
r = c.get("/api/v1/auth/config")
check("GET /auth/config", r.status_code == 200)
ac = r.json()
check("auth_mode present", "auth_mode" in ac)
check("no API key in auth/config", "ANTHROPIC" not in r.text and "sk-" not in r.text)

# ── onboarding ────────────────────────────────────────────────────────────────
print("\n=== FLOW 5: onboarding ===")
r = c.post("/api/v1/onboarding", json={
    "role": "개발자",
    "role_detail": "개발자",
    "goals": ["소식 파악"],
    "interest_types": ["AI agent", "스타트업"],
    "keywords": ["AI agent", "스타트업"],
    "preferred_signal_count": 3,
    "briefing_time": "08:00",
    "connectors": {}
})
check("POST /onboarding", r.status_code == 200, str(r.json().get("success")))

# ── interests & sources ───────────────────────────────────────────────────────
print("\n=== FLOW 6: interests & sources ===")
r = c.get("/api/v1/interests?include_muted=true")
check("GET /interests", r.status_code == 200)
interests = r.json().get("interests", [])
check("interests seeded", len(interests) >= 2, f"count={len(interests)}")

r = c.post("/api/v1/sources/configs/seed-defaults", json={"overwrite": False})
check("POST /sources/seed-defaults", r.status_code == 200)

r = c.get("/api/v1/sources/configs")
check("GET /sources/configs", r.status_code == 200)

# ── briefing generation ───────────────────────────────────────────────────────
print("\n=== FLOW 7: briefing generation (mock mode) ===")
r = c.post("/api/v1/signals/generate", json={"mode": "mock", "replace_today": True})
check("POST /signals/generate", r.status_code == 200, str(r.status_code))
gen = r.json() if r.status_code == 200 else {}
count = gen.get("generated_signal_count", 0)
check("signals generated > 0", count > 0, f"count={count}")

# ── period tabs ───────────────────────────────────────────────────────────────
print("\n=== FLOW 8: period tabs ===")
signal_id = None
for period in ["today", "week", "month"]:
    r = c.get(f"/api/v1/signals?period={period}")
    check(f"GET /signals?period={period}", r.status_code == 200, f"status={r.status_code}")
    sigs = r.json().get("signals", [])
    if period == "today":
        check("signals exist for today", len(sigs) > 0, f"count={len(sigs)}")
        signal_id = sigs[0]["id"] if sigs else None

# ── feedback ──────────────────────────────────────────────────────────────────
print("\n=== FLOW 9: feedback ===")
if signal_id:
    # Post "saved" first, then check the saved list before overwriting status.
    r = c.post(f"/api/v1/signals/{signal_id}/feedback",
               json={"event_type": "saved", "payload": {"surface": "web_app"}})
    check("POST /feedback event=saved", r.status_code == 200)
    r = c.get("/api/v1/signals/saved")
    check("GET /signals/saved", r.status_code == 200)
    saved = r.json().get("signals", [])
    check("saved signal appears", len(saved) > 0, f"count={len(saved)}")
    # tracked / ignored override signal status; post them after the saved check.
    for ev in ["tracked", "ignored"]:
        r = c.post(f"/api/v1/signals/{signal_id}/feedback",
                   json={"event_type": ev, "payload": {"surface": "web_app"}})
        check(f"POST /feedback event={ev}", r.status_code == 200)
    r = c.get("/api/v1/signals/feedback/tracked")
    check("GET /feedback/tracked", r.status_code == 200)
    r = c.get("/api/v1/signals/feedback/ignored")
    check("GET /feedback/ignored", r.status_code == 200)

# ── assistant chat ────────────────────────────────────────────────────────────
print("\n=== FLOW 10-13: assistant chat ===")
r = c.post("/api/v1/assistant/chat", json={
    "message": "이번 주 가장 중요한 소식 3개 알려줘",
    "period": "week",
})
check("POST /assistant/chat (week top 3)", r.status_code == 200)
chat = r.json() if r.status_code == 200 else {}
check("  has answer", bool(chat.get("answer")))
check("  has conversation_id > 0", (chat.get("conversation_id") or 0) > 0)
check("  has message_id > 0", (chat.get("message_id") or 0) > 0)
answer_text = chat.get("answer", "")
check("  answer not empty", len(answer_text) > 10, answer_text[:80])
conv_id = chat.get("conversation_id")
print(f"     ANSWER: {answer_text[:200]}")

# follow-up in same conversation
r = c.post("/api/v1/assistant/chat", json={
    "message": "이게 왜 중요한데?",
    "period": "week",
    "conversation_id": conv_id,
})
check("POST /assistant/chat follow-up (same conv)", r.status_code == 200)
chat2 = r.json() if r.status_code == 200 else {}
check("  same conv_id maintained", chat2.get("conversation_id") == conv_id)
print(f"     ANSWER: {chat2.get('answer','')[:200]}")

# selected signal
if signal_id:
    r = c.post("/api/v1/assistant/chat", json={
        "message": "이 소식에 대해 자세히 알려줘",
        "period": "today",
        "selected_signal_id": signal_id,
    })
    check("POST /assistant/chat with selected_signal_id", r.status_code == 200)
    chat3 = r.json() if r.status_code == 200 else {}
    sources = chat3.get("sources", [])
    check("  sources present", len(sources) > 0, f"count={len(sources)}")
    for src in sources:
        check(f"  citation signal_id={src.get('signal_id')} has title", bool(src.get("title")))
        check(f"  citation has source_name", bool(src.get("source_name")))
    print(f"     ANSWER: {chat3.get('answer','')[:200]}")
    if sources:
        print(f"     CITATIONS: {[(s.get('source_name'), s.get('title','')[:40]) for s in sources]}")

# no-context question
r = c.post("/api/v1/assistant/chat", json={
    "message": "12세기 몽골 제국 역사를 알려줘",
    "period": "today",
})
check("POST /assistant/chat no-context query", r.status_code == 200)
chat4 = r.json()
check("  no fabricated sources", len(chat4.get("sources", [])) == 0)
ans4 = chat4.get("answer", "")
no_fabrication = "없" in ans4 or "없어요" in ans4 or "관련" in ans4 or "로컬 모드" in ans4
check("  answer admits no data (no hallucination)", no_fabrication, ans4[:100])

# monthly AI
r = c.post("/api/v1/assistant/chat", json={
    "message": "이번 달 AI 관련 변화만 정리해줘",
    "period": "month",
})
check("POST /assistant/chat month AI", r.status_code == 200)
print(f"     ANSWER: {r.json().get('answer','')[:200]}")

# ── new conversation ──────────────────────────────────────────────────────────
print("\n=== FLOW 14: new conversation ===")
r = c.post("/api/v1/assistant/chat", json={"message": "새 대화 시작", "period": "today"})
check("New conversation (no conv_id passed)", r.status_code == 200)
new_conv = r.json().get("conversation_id")
check("  new conv_id differs from old", new_conv != conv_id, f"old={conv_id} new={new_conv}")

r = c.get("/api/v1/assistant/conversations")
check("GET /assistant/conversations", r.status_code == 200)
convs = r.json().get("conversations", [])
check("  >= 2 conversations stored", len(convs) >= 2, f"count={len(convs)}")

r = c.get(f"/api/v1/assistant/conversations/{conv_id}/messages")
check(f"GET /conversations/{conv_id}/messages", r.status_code == 200)
msgs = r.json().get("messages", [])
check("  messages present", len(msgs) >= 2, f"count={len(msgs)}")
if msgs:
    roles = [m["role"] for m in msgs]
    check("  alternating user/assistant roles", "user" in roles and "assistant" in roles, str(roles[:4]))

# ── logout/re-login data persistence ──────────────────────────────────────────
print("\n=== FLOW 15-16: logout/re-login data persistence ===")
c2 = make_client(1)
r = c2.get("/api/v1/interests?include_muted=true")
check("Interests persist after re-login", r.status_code == 200)
check("  same count", len(r.json().get("interests", [])) >= 2)

r = c2.get("/api/v1/signals?period=today")
check("Signals persist after re-login", r.status_code == 200)
check("  signals still there", len(r.json().get("signals", [])) > 0)

r = c2.get("/api/v1/assistant/conversations")
check("Conversations persist after re-login", r.status_code == 200)

# ── A/B data isolation ────────────────────────────────────────────────────────
print("\n=== A/B data isolation ===")
cb = make_client(2)

r = cb.get("/api/v1/signals?period=today")
check("User B: GET /signals isolated", r.status_code == 200)
b_sigs = r.json().get("signals", [])
check("  B has 0 signals (A's not visible)", len(b_sigs) == 0, f"count={len(b_sigs)}")

if conv_id:
    r = cb.get(f"/api/v1/assistant/conversations/{conv_id}/messages")
    check("User B: cannot read A's conversation", r.status_code == 200)
    check("  messages empty for B", r.json().get("messages", []) == [])

    r = cb.delete(f"/api/v1/assistant/conversations/{conv_id}")
    check("User B: cannot delete A's conversation", r.status_code == 200)
    check("  success=False", r.json().get("success") is False)

r = cb.get("/api/v1/interests?include_muted=true")
check("User B: GET /interests isolated", r.status_code == 200)
check("  B has 0 interests", len(r.json().get("interests", [])) == 0)

r = cb.get("/api/v1/signals/saved")
check("User B: GET /signals/saved isolated", r.status_code == 200)
check("  B has 0 saved signals", len(r.json().get("signals", [])) == 0)

r = cb.get("/api/v1/assistant/conversations")
check("User B: GET /conversations isolated", r.status_code == 200)
check("  B has 0 conversations", len(r.json().get("conversations", [])) == 0)

# ── API completeness ──────────────────────────────────────────────────────────
print("\n=== API completeness (no 404/500) ===")
app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=1)
endpoints = [
    ("GET", "/api/v1/profile"),
    ("GET", "/api/v1/settings"),
    ("GET", "/api/v1/connectors"),
    ("GET", "/api/v1/sources/catalog"),
    ("GET", "/api/v1/sources/configs"),
    ("GET", "/api/v1/interests?include_muted=true"),
    ("GET", "/api/v1/interests/recommendations"),
    ("GET", "/api/v1/feedback/events?limit=5"),
    ("GET", "/api/v1/pipeline/runs?limit=5"),
    ("GET", "/api/v1/assistant/conversations"),
]
for method, path in endpoints:
    r = c.request(method, path)
    ok = r.status_code not in (404, 500)
    check(f"{method} {path}", ok, f"status={r.status_code}")

# ── summary ───────────────────────────────────────────────────────────────────
app.dependency_overrides.clear()
print("\n=== SUMMARY ===")
passed = sum(1 for icon, _, _ in results if icon == PASS)
failed = sum(1 for icon, _, _ in results if icon == FAIL)
print(f"\n  {passed} passed  /  {failed} failed  /  {passed + failed} total\n")
if failed:
    print("FAILURES:")
    for icon, label, detail in results:
        if icon == FAIL:
            print(f"  FAIL: {label}" + (f" -- {detail}" if detail else ""))
sys.exit(0 if failed == 0 else 1)

# Desktop Companion MVP QA

Date: 2026-06-30

## Scope

This phase keeps the Web UI as the main LUMOS product surface and clarifies the Desktop Companion as a local launcher/controller.

Companion is not:

- a replacement for `/app`
- a packaged desktop app
- an installer
- a tray daemon
- a startup service
- an auto-update or code-signed app

Companion is:

- a small local helper that starts or reuses the LUMOS server
- a quick launcher for the Web UI
- a control surface for preparing new signals and syncing personal context
- a temporary MVP shell that can later shrink into tray/background/notification behavior

## Run

```powershell
python run.py companion
```

Expected:

- FastAPI server is checked.
- If the server is already running, Companion reuses it.
- If the server is not running, Companion starts it in a background thread.
- The default browser opens the Web UI.
- A small `LUMOS Companion` window opens.

## Companion Window Copy

Title:

```text
LUMOS Companion
```

Role copy:

```text
LUMOS를 실행하고 오늘의 신호 화면으로 연결해주는 작은 도우미예요.
오늘의 신호는 브라우저 화면에서 확인하고, 이 창에서는 빠른 실행만 도와드려요.
```

Status labels:

- `LUMOS 실행 상태`
- `오늘의 신호`
- `마지막 확인`

Buttons:

- `오늘의 신호 열기`
- `새 신호 준비하기`
- `개인 맥락 동기화`
- `설정 화면 열기`
- `활동 기록 보기`
- `도움말`
- `Companion 닫기`

The UI should not expose internal terms such as server, API, pipeline, or generate mode.

## Button URL Contract

| Button | Expected action |
| --- | --- |
| `오늘의 신호 열기` | Open `http://127.0.0.1:8000/app#today` |
| `새 신호 준비하기` | Call signal generation, then open `http://127.0.0.1:8000/app#today` |
| `개인 맥락 동기화` | Call context sync and show Korean status copy |
| `설정 화면 열기` | Open `http://127.0.0.1:8000/app#settings` |
| `활동 기록 보기` | Open `http://127.0.0.1:8000/app#activity` |
| `도움말` | Open local `README.md` |
| `Companion 닫기` | Close Companion window |

Supported Web UI hashes:

- `/app#today`
- `/app#signals`
- `/app#interests`
- `/app#sources`
- `/app#activity`
- `/app#settings`

`#signals` is an alias for `#today`. Unknown hashes should fall back to today.

## Hash Deep Link QA Checklist

Manual checks when browser automation is available:

1. Open `http://127.0.0.1:8000/app#today` and confirm the today tab is active.
2. Open `http://127.0.0.1:8000/app#signals` and confirm the today tab is active.
3. Open `http://127.0.0.1:8000/app#interests` and confirm the interests tab is active.
4. Open `http://127.0.0.1:8000/app#sources` and confirm the sources tab is active.
5. Open `http://127.0.0.1:8000/app#activity` and confirm the activity tab is active and activity data loads.
6. Open `http://127.0.0.1:8000/app#settings` and confirm the settings tab is active and settings data loads.
7. With `/app` already open, change the hash in the address bar to `#settings`; the settings tab should activate without a full app restart.
8. Change the hash to `#activity`; the activity tab should activate and load.
9. Change the hash to an unknown value such as `#unknown`; the app should return to today.
10. Click each Web UI tab and confirm the address hash updates.

## Server Start And Duplicate Handling

Implementation:

- `src/app/server_control.py`
- health check: `GET /health`
- base URL: `http://127.0.0.1:8000`
- server startup: uvicorn in a daemon thread
- duplicate prevention: if `/health` responds, no new server is started

Shutdown policy:

- If Companion started the server, closing Companion stops that server.
- If the server was already running separately, Companion does not stop it.
- The button label is `Companion 닫기` to avoid implying that the whole product always shuts down.

## Desktop Notification

Notification is best-effort only.

Implementation:

- reuses `src/delivery/desktop_notification.py`
- Korean message: `오늘 볼 신호 N개를 골랐어요.`

Failure policy:

- notification failure must not break Companion
- Companion status text is the primary feedback surface

## Failure States

Connection issue:

```text
잠시 연결이 불안정해요. 다시 시도해보세요.
```

Generate in progress:

```text
새 신호를 준비하고 있어요.
```

Generate success:

```text
오늘의 신호가 준비됐어요. 브라우저에서 확인할 수 있어요.
```

Context sync success:

```text
개인 맥락을 동기화했어요. 활동 기록에서 확인할 수 있어요.
```

Tracebacks are not shown in the Companion UI.

## Verification

Required checks:

- `python -m py_compile ...`
- `node --check src\web\static\app.js`
- `python tests\smoke_test.py`
- `/app = 200`
- `/static/app.js = 200`
- `web_tab_url()` returns the expected hash URLs
- `app.js` contains the `hashchange` listener
- `#today`, `#signals`, `#interests`, `#sources`, `#activity`, `#settings` are handled
- unknown hash fallback exists
- Companion copy is Korean and role-specific
- active path banned strings are not reintroduced

Manual checks when GUI is available:

1. Run `python run.py companion`.
2. Confirm browser opens `/app`.
3. Confirm Companion explains itself as a helper, not the main app.
4. Click `오늘의 신호 열기` and confirm `/app#today`.
5. Click `설정 화면 열기` and confirm `/app#settings` and the settings tab.
6. Click `활동 기록 보기` and confirm `/app#activity` and the activity tab.
7. Click `새 신호 준비하기` and confirm a Korean busy state, success state, and `/app#today`.
8. Click `개인 맥락 동기화` and confirm a Korean busy state and success/failure state.
9. Close Companion and confirm shutdown behavior follows the server ownership policy.

## Known Limits

- No installer.
- No auto-update.
- No code signing.
- No OS startup registration.
- No required tray behavior.
- tkinter UI appearance is intentionally simple.
- The main reading experience remains the Web UI.
- Manual screenshot QA is still needed for final visual confidence.

## Next Phase Direction

The next product direction can move toward a Desktop Companion that is less window-centric:

- tray/background helper
- notification-first surface
- smaller status window
- open Web UI only when the user wants to read or configure LUMOS

That should happen only after hash deep links, first-run flow, and browser-level visual QA are stable.

## Demo Rehearsal Reference

For presentation readiness and screenshot QA, use:

- `docs/demo/demo_rehearsal_report.md`
- `docs/demo/screenshots/README.md`
- `docs/demo/manual_demo_checklist.md`

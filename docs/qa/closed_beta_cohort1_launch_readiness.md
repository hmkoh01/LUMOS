# Closed Beta Cohort 1 Launch Readiness

Phase: Closed Beta Cohort 1 Launch Readiness Gate  
Date: 2026-07-07  
Decision: Almost ready

## Artifact

- File: `dist/LUMOS-0.1.0-alpha-portable.zip`
- Version: `0.1.0-alpha`
- Size: `28,659,565 bytes`
- SHA256: `2074F5780806D71703D6A5D581A5708B10A41A1C1479EF60C021D143621084C5`
- Distribution: selected closed beta users only

## QA Environment

Current verified environment:

- OS: `Microsoft Windows NT 10.0.26200.0`
- Python installed: Yes, `Python 3.9.21`
- PyInstaller: `6.21.0`
- Existing LUMOS development environment: Yes
- Network: Connected
- Cloud backend: Not required, not used for packaged local mode QA
- Admin rights: Not required for normal app execution in this pass

Not yet verified:

- Python-free clean Windows 11
- Python-free clean Windows 10
- Separate clean VM or separate laptop

## Clean Windows Execution

Result: Not completed

Reason:

- This session has access to the current development Windows machine only.
- A Python-free clean Windows environment or VM was not available from the current workspace.

Current substitute checks:

- Packaged `LUMOS.exe` launched directly from `dist/LUMOS/`.
- Local server responded without starting cloud backend.
- `/app#today` opened in browser.
- Route, generate, feedback, persistence checks passed in packaged runtime.

Launch implication:

- Cohort 1 external delivery should wait for one Python-free clean Windows run.
- If no clean machine is available, first Cohort 1 recipient should be treated as an installation canary, not a general beta user.

## Clean Zip Execution QA

Result: Pass on development Windows machine

Checked:

- `dist/LUMOS-0.1.0-alpha-portable.zip` exists.
- Zip does not include `.db`, `.db-wal`, `.db-shm`, `.env`, token/cache/log files.
- `LUMOS.exe` exists.
- beta package documents exist.
- `tkinter/test` packaging noise removed.
- Cloud backend is not required for local mode.

Packaged route results:

- `/health`: 200
- `/app`: 200
- `/`: 200
- `/pricing`: 200
- `/download`: 200
- `/beta`: 200
- `/static/app.js`: 200
- `/landing-static/landing.js`: 200

## SmartScreen / Antivirus / Firewall

Result: Not fully verified

Current status:

- No SmartScreen, Defender, antivirus, or firewall warning was captured in this development-machine pass.
- This is not sufficient to conclude that beta users will not see warnings.
- Because the artifact is unsigned, Windows SmartScreen warning remains likely for some users.

Prepared user guidance:

- `packaging/windows/beta_package/README_FIRST.md`
- `packaging/windows/beta_package/KNOWN_ISSUES.md`
- `README.md`
- `src/web/landing/download.html`
- `src/web/landing/beta.html`

Guidance principle:

- Do not tell users to blindly ignore security warnings.
- Explain that the alpha portable build is before code signing.
- Provide only through a trusted closed beta channel.
- Tell users to stop and ask if unsure.

Screenshots:

- `docs/demo/screenshots/closed_beta/10_smartscreen_warning.png`: not captured
- `docs/demo/screenshots/closed_beta/11_firewall_warning.png`: not captured
- `docs/demo/screenshots/closed_beta/12_antivirus_warning.png`: not captured

## Companion Visible QA

Result: Pass on development Windows machine

Checked:

- `LUMOS Companion` window appeared.
- Korean text was readable.
- Companion explained that it is a small local helper, not the main app.
- Buttons were visible:
  - 오늘의 신호 열기
  - 새 신호 준비하기
  - 개인 맥락 동기화
  - 설정 화면 열기
  - 활동 기록 보기
  - 도움말
  - Companion 닫기
- Account line showed local mode.
- Cloud connection was described as a settings-screen item.

Screenshot:

- `docs/demo/screenshots/closed_beta/02_companion_visible.png`

Remaining:

- DPI 100% / 125% / 150% verification on clean Windows.

## Browser / Onboarding Click QA

Result: Partial pass

Confirmed:

- Browser opened to `http://127.0.0.1:8000/app#today`.
- First-run CTA was visible in screenshot.
- Product API flow generated 3 signals.
- Feedback API saved an event.

Not completed:

- Full mouse/keyboard click path from `시작하기` through onboarding Step 1/2/3.
- Visual confirmation of loading state during signal generation.
- Manual click on details, 저장, 관심 없음, 계속 추적.

Reason:

- Browser automation execution tool was not available in this session.
- A separate manual clean Windows run is still required.

## Signal / Feedback / Persistence

Result: Pass in packaged runtime

Packaged runtime QA:

- Generate with mock mode returned 3 signals.
- `/api/v1/signals/today` returned 3 signals.
- Feedback event `saved` succeeded.
- Reopen with the same `LUMOS_DATA_DIR` preserved 3 signals.
- `lumos.db` was created in the chosen data directory.
- Cloud backend was not required.

## DPI / Layout QA

Result: Partial pass

Confirmed:

- Current display screenshot showed Companion text and buttons without clipping.
- Web UI first-run screen was readable in the captured desktop.

Not completed:

- 100% scaling explicit check
- 125% scaling explicit check
- 150% scaling explicit check

Launch implication:

- Cohort 1 should include a question asking whether Companion or Web UI text was clipped.

## Launch Pack

Prepared:

- `docs/product/cohort1_launch_pack.md`
- `docs/product/beta_email_templates.md`
- `docs/product/beta_feedback_tracker.md`

Launch pack includes:

- Cohort 1 goals
- target users
- artifact name and SHA256
- delivery method
- first email summary
- known issues
- feedback questions
- 3-day and 7-day follow-up
- go/no-go criteria
- metrics to collect

## Go / No-go Evaluation

Ready criteria status:

- Python-free clean Windows execution: Not completed
- Companion visible: Pass on development Windows
- Browser `/app#today`: Pass on development Windows
- Click-based onboarding: Not completed
- Signal 3 generated: Pass
- Feedback saved: Pass
- Close/reopen/persistence: Pass
- SmartScreen/antivirus guidance: Prepared
- Zip sensitive file scan: Pass
- beta email/templates: Prepared
- feedback tracker: Prepared

Final judgment: Almost ready

Reason:

- The portable artifact is technically functional in the development Windows environment.
- The package is clean of local DB, env, token/cache/log files.
- User-facing Korean copy and beta documents are now readable.
- Launch operation documents are prepared.
- However, the core gate requirement of Python-free clean Windows execution and full click-based onboarding has not yet been completed.

## Remaining Blockers

Before sending to 3-5 Cohort 1 users:

1. Run `LUMOS.exe` on a Python-free clean Windows 10/11 environment.
2. Capture SmartScreen/Defender/firewall state.
3. Complete full click-based onboarding.
4. Confirm signal card details and feedback buttons visually.
5. Confirm Companion at 100%, 125%, and 150% DPI if possible.

## Recommended Next Phase

Closed Beta Cohort 1 Canary Run:

- Send the artifact to 1 trusted canary user first.
- Treat that user as the clean Windows validation target.
- Collect installation screenshots and security warning state.
- If canary succeeds, expand to 3-5 Cohort 1 users.

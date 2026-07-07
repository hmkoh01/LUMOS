# MVP Reality Check & Briefing Quality QA

Date: 2026-06-25

## Scope

This QA pass focused on whether the current local MVP is understandable and usable for a first-time Korean user. It did not add collectors, login, payment, tray/startup behavior, React/Vite/Next.js, or external LLM calls.

## Test Environment

- OS shell: PowerShell
- App entry: `python run.py app`
- API server check: `python run.py api`
- Web entry: `http://127.0.0.1:8000/app`
- Automated browser availability: unavailable in this session. The browser skill requires a Node REPL execution tool, but tool discovery returned no callable Node REPL browser tool.

## Commands Run

```powershell
python tests\smoke_test.py
python -m py_compile run.py src\app\main.py src\api\feedback.py src\storage\sqlite_store.py src\signals\generator.py src\signals\mock_generator.py src\signals\korean_briefing.py
node --check src\web\static\app.js
```

Server response check:

```text
/app = 200
/static/app.js = 200
```

## Browser QA Status

Automated browser interaction was not possible in this environment. Instead, the pass covered:

- FastAPI serving checks for `/app` and `/static/app.js`
- static DOM presence for onboarding sections
- JavaScript syntax validation
- CSS responsive structure inspection
- temporary database first-run API scenario
- smoke test coverage for Web UI strings and Korean briefing serialization

Manual viewport checklist to run when a browser automation surface is available:

- 1440x900: first-run panel, onboarding modal, signal card, settings grid
- 1366x768: hero height, first-run CTA visibility, signal card fold
- 1280x800: sidebar/content balance, card width, details readability
- 390x844: top nav scroll, onboarding modal scroll, button wrapping

## Screens Checked By Static/Server QA

- First-run today's signals surface
- Onboarding Step 1 DOM
- Onboarding Step 2 DOM
- Onboarding Step 3 DOM
- Today's signal card renderer
- Interest empty state and interest cards
- Source empty state and source cards
- Activity empty state and activity renderer
- Settings form
- Signal details renderer with original title/snippet

## First-Run Scenario

Clean state was verified with a temporary SQLite database.

Initial state:

- profile: `None`
- `onboarding_completed`: `False`
- active interests: `[]`
- today signals: `[]`

Expected result:

- Web JS detects first-run through profile/settings/interests/signals.
- The first-run panel shows `시작하기`.
- User does not need to visit Settings first.

Result: pass.

## Onboarding E2E

Temporary DB flow:

1. Save onboarding with role `예비 창업자 / PM`.
2. Save three keywords: `AI agent`, `생산성 툴`, `GitHub 트렌드`.
3. Save briefing count `3` and time `08:00`.
4. Disable browser/local file connectors.
5. Seed default sources.
6. Generate today's signals in mock mode.

Observed:

- profile saved
- settings saved
- connector state saved
- interests created from onboarding
- default source config available
- 3 signals generated
- all generated signals include Korean display fields

Result: pass.

## Empty State QA

| State | Expected copy/action | Result |
| --- | --- | --- |
| Today's signals empty | `지금 새로 받아보면 관심사에 맞는 변화를 한국어로 정리해드릴게요.` / `지금 새로 받기` | pass |
| Interests empty | `관심 키워드를 추가하면 더 정확한 신호를 받을 수 있어요.` / `관심사 추가하기` | pass |
| Sources empty | `Hacker News, GitHub, RSS 중 하나를 켜면 신호를 만들 수 있어요.` / `기본 소스 켜기` | pass |
| Activity empty | `오늘의 신호를 받으면 이곳에 기록이 남아요.` | pass |
| API failure | `잠시 연결이 불안정해요. 다시 시도해보세요.` | pass by code inspection |
| Partial source failure | `일부 소스에서 데이터를 가져오지 못했지만...` | pass by code inspection |

## Feedback Action QA

Temporary DB flow verified:

- Generated a signal.
- Posted `saved` feedback to `/api/v1/signals/{signal_id}/feedback`.
- Read `/api/v1/feedback/events`.

Result:

- feedback event persisted
- response status was 200
- Web action code still calls existing feedback API
- Korean toast messages exist for saved/ignored/tracked/opened

## Issues Found

1. Korean briefing helper produced repetitive summary/action patterns.
2. Some common keyword topics were not normalized before display.
3. Signal card could become tall when summary or explanation text was long.
4. Automated visual viewport checks could not be performed because the browser execution tool was unavailable.

## Fixes Applied

- Added common topic normalization in `src/signals/korean_briefing.py`.
- Reworked generated summary and action copy to reduce repetition.
- Added line clamping for signal summary and info-box text in `styles.css`.
- Kept original title/snippet in details.

## Remaining Issues

- Korean briefing is rule-based and is not a full translation layer.
- Visual QA should be repeated with real browser screenshots.
- Details still contains a small technical box for score/run context. It is hidden by default, but a future pass should convert it into friendlier labels.

## Next Phase Suggestions

- Run screenshot-based QA across desktop and mobile viewports.
- Add a small fixture-based visual regression test for first-run and generated-card states.
- Improve Korean briefing with source-specific templates before introducing any LLM dependency.
- Add a lightweight in-app “add interest” flow outside onboarding.

---

# Manual Browser QA Fix Pass

Date: 2026-06-26

## Browser QA Availability

Automated browser QA was attempted again. Tool discovery for the required Node REPL browser execution surface returned no callable tool, so the agent could not drive the in-app browser or capture screenshots directly.

Because of that limitation, this pass used:

- static HTML/CSS/JS inspection
- FastAPI `/app` and `/static/app.js` serving checks
- JavaScript syntax check
- Python compile check
- smoke test
- temporary database fresh-user scenario
- manual QA checklist hardening

## Recommended Manual QA Procedure

Run:

```powershell
python run.py app
```

Open:

```text
http://127.0.0.1:8000/app
```

Use these viewport sizes:

- 1440x900
- 1366x768
- 1280x800
- 390x844

For each viewport, check:

- no horizontal page overflow
- current tab is visually obvious
- primary CTA is easy to find
- buttons do not collide or wrap awkwardly
- Korean copy remains readable
- details sections are closed by default
- modal content scrolls if needed

## Screen Checklist

### First-run Start Screen

Pass criteria:

- Brand and short description are visible.
- `오늘 꼭 봐야 할 신호` is visible as the main task.
- `시작하기` CTA is prominent.
- User can understand the next action without opening Settings.

### Onboarding Step 1

Pass criteria:

- Step indicator is visible.
- Role choices are large enough to scan.
- `직접 입력` is optional and does not dominate the screen.

### Onboarding Step 2

Pass criteria:

- Keyword input explains comma/enter behavior through the UI pattern.
- Suggested keywords are visible and tappable.
- Added tags are easy to distinguish and remove.
- Empty keyword submission shows a Korean toast.

### Onboarding Step 3

Pass criteria:

- `3개`, `08:00`, and `혼합 모드` defaults are clear.
- Personal context copy does not create privacy anxiety.
- `오늘의 신호 받기` is the clear final action.

### Today's Signal Cards

Pass criteria:

- Three cards are readable without feeling like a developer list.
- Korean title and summary appear before source details.
- `왜 중요한가`, `왜 나에게 추천됐나요?`, `다음에 볼 것` have clear hierarchy.
- `저장`, `관심 없음`, `계속 추적`, `원문 보기` roles are distinguishable.
- Default card does not expose English source text excessively.

### Signal Details Open

Pass criteria:

- Original title and snippet appear as supporting information.
- Technical information is not shown as raw JSON.
- Generation mode and briefing record are described in user language.
- Source warning copy is calm and non-alarming.

### My Interests

Pass criteria:

- Importance is shown as `높음`, `보통`, or `낮음`.
- Evidence is sentence-based, not JSON.
- Hide, restore, delete, and weight actions are understandable.

### Sources

Pass criteria:

- Source state chips are easy to understand.
- RSS URLs are edited as lines, not JSON.
- GitHub token copy is optional and not blocking.
- Prepared/disabled/upcoming states are visually distinct.

### Activity

Pass criteria:

- Activity reads like “what LUMOS did,” not a console log.
- Raw JSON is hidden by default.
- Details are optional.

### Settings

Pass criteria:

- Daily briefing, personal context, and generation mode are separated.
- Mode labels stay user-facing: `안정 모드`, `혼합 모드`, `실제 소스 모드`.
- The screen does not require a first-time user to understand internal concepts.

## Capture Guide

Capture these screens during manual QA:

1. First-run start screen
2. Onboarding Step 1
3. Onboarding Step 2
4. Onboarding Step 3
5. Today's signal screen with 3 cards
6. Signal details opened
7. My Interests tab
8. Sources tab
9. Activity tab
10. Settings tab

Recommended naming:

```text
qa-1440-first-run.png
qa-1440-onboarding-step-1.png
qa-1440-onboarding-step-2.png
qa-1440-onboarding-step-3.png
qa-1440-signals-3-cards.png
qa-1440-signal-details-open.png
qa-1440-interests.png
qa-1440-sources.png
qa-1440-activity.png
qa-1440-settings.png
qa-390-first-run.png
qa-390-onboarding-step-3.png
qa-390-signals.png
```

## Visual/UX Issues Found In Static Pass

1. Signal details still included a raw JSON-like technical box.
2. Long signal summaries and explanation text could make a card feel tall.
3. Full screenshot validation is still pending because browser automation is unavailable.

## Fixes Applied In This Pass

- Replaced the signal details raw technical JSON block with a user-language `브리핑 참고 정보` box.
- Kept original title and snippet in supporting details.
- Retained line clamping for default signal summary and info sections.
- Preserved details as closed by default.

## Remaining Issues

- Activity details still include raw JSON in a hidden developer-style box. It is not visible by default, but should be converted to friendly labels in a later polish pass.
- Visual QA still needs actual browser screenshots.
- Mobile 390px layout should be manually checked before presenting the MVP externally.

## Desktop Companion Readiness

Judgment: **Almost Ready**

Reasoning:

- First-run E2E passes with a temporary clean database.
- `/app` supports onboarding, signal generation, Korean signal cards, and feedback actions.
- Korean briefing quality is minimally usable for MVP.
- Empty states are friendly and action-oriented.
- Signal details no longer expose the most obvious raw technical box.
- The main blocker is lack of actual screenshot-based visual QA. This does not block exploratory Desktop Companion work, but it should be completed before a user demo.

Criteria check:

| Criterion | Result |
| --- | --- |
| First-run E2E is stable | Pass |
| Today's signal cards are readable by static QA | Pass with pending visual confirmation |
| Korean briefing is minimally usable | Pass |
| Core actions work from `/app` | Pass |
| Empty states are friendly | Pass |
| Feedback action works | Pass |
| Remaining UI issues block Desktop Companion | No, but screenshot QA is pending |

## Desktop Companion Clarification

The Desktop Companion is now treated as a local launcher/controller, not the main product surface. The main user-facing screen remains the Web UI at `/app`.

Companion deep link QA and button-level expectations are tracked in:

- `docs/qa/desktop_companion_mvp.md`

Before presenting the MVP externally, manually confirm that:

- `오늘의 신호 열기` opens `/app#today`
- `설정 화면 열기` opens `/app#settings`
- `활동 기록 보기` opens `/app#activity`
- an already-open `/app` screen switches tabs when the hash changes
- Companion copy does not make the small window feel like the full app

## Demo And User Test Documents

Use the demo documents before mentoring, presentation, or first user testing:

- `docs/demo/demo_flow.md`
- `docs/demo/pitch_demo_script.md`
- `docs/demo/user_test_script.md`
- `docs/demo/manual_demo_checklist.md`
- `docs/demo/demo_data_strategy.md`
- `docs/demo/next_priorities_after_user_test.md`
- `docs/demo/demo_rehearsal_report.md`
- `docs/demo/screenshots/README.md`

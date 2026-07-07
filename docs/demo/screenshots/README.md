# Screenshot QA Index

Date: 2026-06-30

## Status

Screenshot generation was **not performed** in this environment.

Reason:

- The browser automation execution tool was not available in this session.
- GUI launching/clicking from the sandbox is not reliable enough for real Companion and browser screenshots.

This document is the required manual capture guide for the next live Windows rehearsal.

## Recommended Viewports

Capture at least:

- 1366x768
- 1440x900

If time allows:

- 1280x800
- 390x844

Browser zoom:

- 90-100%

## Required Screenshot List

| File | Screen | QA Purpose | Status |
| --- | --- | --- | --- |
| `01_companion_window.png` | Companion window | Role clarity, button labels, close behavior | Pending |
| `02_first_run_today.png` | First-run today screen | CTA visibility, next action clarity | Pending |
| `03_onboarding_step_1.png` | Onboarding Step 1 | Role selection clarity | Pending |
| `04_onboarding_step_2.png` | Onboarding Step 2 | Keyword tag input clarity | Pending |
| `05_onboarding_step_3.png` | Onboarding Step 3 | Defaults, privacy copy, final CTA | Pending |
| `06_today_signals.png` | Today with 3 signal cards | Card density, Korean briefing readability | Pending |
| `07_signal_details_open.png` | Signal details opened | Original source preservation, non-technical details | Pending |
| `08_interests_tab.png` | Interests tab | Importance labels, action clarity | Pending |
| `09_sources_tab.png` | Sources tab | Source state clarity, no JSON editing | Pending |
| `10_activity_tab.png` | Activity tab | Friendly activity log, raw JSON hidden | Pending |
| `11_settings_tab.png` | Settings tab | Settings grouping and mode labels | Pending |
| `12_companion_settings_deeplink.png` | Companion settings deep link | `/app#settings` activates settings tab | Pending |
| `13_companion_activity_deeplink.png` | Companion activity deep link | `/app#activity` activates activity tab | Pending |

## Manual Capture Procedure

1. Open PowerShell in the project root.
2. Run:

   ```powershell
   python run.py companion
   ```

3. Capture `01_companion_window.png`.
4. Click `오늘의 신호 열기`.
5. Capture `02_first_run_today.png`.
6. Complete onboarding:
   - role: `예비 창업자 / PM`
   - keywords: `AI agent`, `생산성 툴`, `스타트업`
   - count: `3`
   - mode: `혼합 모드` if stable, otherwise `안정 모드`
7. Capture each onboarding step.
8. Click `오늘의 신호 받기`.
9. Capture `06_today_signals.png`.
10. Open one signal's `자세히 보기`.
11. Capture `07_signal_details_open.png`.
12. Navigate to each tab and capture:
    - interests
    - sources
    - activity
    - settings
13. From Companion, click `설정 화면 열기` and capture the active settings tab.
14. From Companion, click `활동 기록 보기` and capture the active activity tab.

## Pass Criteria

Companion:

- The window reads as a helper, not the main app.
- Buttons are understandable.
- No internal terms are visible.

First-run:

- `시작하기` is visible without searching.
- The next action is clear.

Onboarding:

- Step progression is visible.
- Keyword entry is understandable.
- Defaults are not intimidating.

Signal cards:

- Korean title and summary are prominent.
- Card sections are readable.
- Buttons are not cramped.
- English source text is not prominent in the default card.

Details:

- Original title/snippet are supporting information.
- Technical information is phrased for users.
- Details are not visually dominant.

Tabs:

- Active tab state is obvious.
- Settings/activity deep links land on the correct tab.

## Findings

No screenshot findings yet. Fill this section after manual capture.

Template:

```text
File:
Viewport:
Result: Pass / Hold / Needs Fix
Finding:
Fix needed:
```

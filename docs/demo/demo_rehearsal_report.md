# Demo Rehearsal Report

Date: 2026-06-30

## Summary

Phase: Demo Rehearsal & Screenshot QA

Judgment: **Almost Ready**

Reason:

- Core demo flow is documented and technically smoke-tested.
- `/app` and static Web UI serving are verified.
- Companion import and deep link helper are covered by smoke tests.
- First-run, Korean briefing fields, feedback loop, and Web UI hashes are covered by existing automated checks.
- Actual GUI clicking and screenshot capture were not completed in this environment because the browser automation execution tool was not available and launching GUI apps from the sandbox is not reliable.

The MVP can move to a live rehearsal on the target Windows machine, but should not be treated as fully demo-ready until the screenshot checklist in `docs/demo/screenshots/README.md` is completed.

## Test Environment

- OS shell: PowerShell
- Project path: `C:\Users\koh\Desktop\UGRP\2026\LUMOS`
- Date: 2026-06-30
- App entry: `python run.py companion`
- Verified server entry for response checks: `python run.py api`
- Browser automation: unavailable in this session
- Screenshot capture: not performed

## DB State

This pass did not mutate or reset a development DB for GUI rehearsal.

Automated smoke tests use a temporary clean database through FastAPI `TestClient`, so they validate first-run and generation logic without damaging local demo data.

For an actual live demo, use one of:

- clean DB for first-run onboarding demo
- prepared demo DB for time-limited or network-sensitive demo
- stable/mock mode if internet is unreliable

Current stable demo commands:

```powershell
python run.py demo-reset
python run.py demo-seed
python run.py demo-companion
```

See `docs/demo/demo_data_strategy.md`.

## Mode

Recommended live demo mode:

- `hybrid` if network is stable
- stable/mock mode if source access is unstable

This pass did not perform a live source demo in the browser.

## Internet Connection

Not used for screenshot QA in this pass.

Smoke tests use fake collectors and local TestClient flows where possible.

## Demo Flow Rehearsal Status

| Step | Result | Notes |
| --- | --- | --- |
| 1. Companion execution | Static/import verified | Actual GUI launch not performed in sandbox |
| 2. Companion window visible | Not visually verified | Manual Windows check required |
| 3. Browser opens `/app#today` | Helper/static verified | `run.py companion` uses `web_tab_url(BASE_URL, "today")` |
| 4. First-run `시작하기` CTA | Smoke/static verified | Actual screenshot pending |
| 5. Onboarding Step 1 | Smoke/static verified | Actual click pending |
| 6. Onboarding Step 2 keywords | Smoke/static verified | Actual tag input pending |
| 7. Onboarding Step 3 defaults | Smoke/static verified | Actual screenshot pending |
| 8. `오늘의 신호 받기` | Smoke verified | Temporary DB flow passes |
| 9. 3 signal cards | Smoke verified | Visual density screenshot pending |
| 10. Korean card sections | Smoke/static verified | Visual review pending |
| 11. Details original title/snippet | Smoke/static verified | Visual review pending |
| 12. Feedback action | Smoke verified | `tracked` feedback passes |
| 13. Companion `새 신호 준비하기` | Static/import verified | Actual click pending |
| 14. Settings/activity deep link | Helper/static verified | Browser hashchange visual check pending |
| 15. Companion close | Static behavior documented | Manual Windows check required |

## Screens Checked By Static/Automated Verification

- `/app`
- `/static/app.js`
- Web UI hash handling
- First-run/onboarding strings
- Korean display field preference
- Signal details original title/snippet preservation
- Feedback API smoke path
- Companion URL helper
- README/demo document references

## Screens Not Visually Captured

- Companion window
- First-run today screen
- Onboarding Step 1
- Onboarding Step 2
- Onboarding Step 3
- Today signals with 3 cards
- Signal details opened
- Interests tab
- Sources tab
- Activity tab
- Settings tab
- Companion settings deep link
- Companion activity deep link

## Blockers Encountered

Browser automation could not be performed because the browser execution tool was not available in this session. The browser skill instructions were reviewed, but no Node browser execution tool was exposed through tool discovery.

No app-level blocker was found during static/API verification.

## Risks For Live Presentation

1. Companion visual appearance has not been screenshot-reviewed.
2. Signal card density at 1366x768 and 1440x900 is still pending screenshot review.
3. Hash deep link behavior in an already-open real browser must be manually checked.
4. Network-dependent hybrid generation can still fail during a live demo.
5. A messy local DB can bypass first-run onboarding and make the demo flow inconsistent.

## Fixes Applied In This Pass

No product code changes were made.

Documentation updates only:

- Added this rehearsal report.
- Added screenshot QA index and manual capture procedure.
- Added README demo rehearsal references.
- Added QA/demo cross-references.

## Remaining Issues

- Actual screenshot files are not available yet.
- Actual Windows GUI click-through is still required.
- Demo DB preparation remains manual.
- If repeated demos are expected, a future demo DB seed/reset helper may be useful.

## Demo Readiness Judgment

Judgment: **Almost Ready**

Criteria:

| Criterion | Result |
| --- | --- |
| Companion execution is stable | Import/static verified, GUI pending |
| `/app#today` starts correctly | Server/static verified |
| Onboarding is uninterrupted | Smoke verified, visual pending |
| Signal generation finishes within 30 seconds | Smoke passes, live timing pending |
| Korean cards are understandable | Prior QA passes, screenshot pending |
| Feedback buttons work | Smoke passes |
| Settings/activity deep links work | Static/helper verified, browser visual pending |
| Fallback scenario is ready | Documented |

## Go / No-Go For Next Phase

Recommended next step:

- Run one real Windows manual rehearsal with screenshots before user testing.

Can proceed to user testing if:

- the tester is internal or tolerant of MVP rough edges
- stable/mock fallback is prepared
- presenter has `docs/demo/demo_flow.md` and `docs/demo/manual_demo_checklist.md` open

Do not proceed to external/public demo until:

- screenshot checklist is completed
- one full 3-minute rehearsal passes without manual debugging

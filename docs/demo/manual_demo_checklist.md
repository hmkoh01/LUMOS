# Manual Demo Checklist

Date: 2026-06-30

Use this checklist 10 minutes before a demo, mentoring session, or user test.

Related documents:

- Demo flow: `docs/demo/demo_flow.md`
- Rehearsal report: `docs/demo/demo_rehearsal_report.md`
- Screenshot capture guide: `docs/demo/screenshots/README.md`
- Demo data strategy: `docs/demo/demo_data_strategy.md`

## 10-Minute Pre-Demo Checklist

### Environment

- [ ] Correct project directory is open.
- [ ] Virtual environment is activated if needed.
- [ ] Dependencies are installed.
- [ ] No unrelated dev server is using port 8000.
- [ ] Browser is ready.
- [ ] Browser zoom is 90-100%.
- [ ] Recommended viewport is available: 1366x768 or 1440x900.

### Run

- [ ] For a stable presentation demo, run:

  ```powershell
  python run.py demo-reset
  python run.py demo-seed
  python run.py demo-companion
  ```

- [ ] Confirm the console says the demo DB is used.
- [ ] Confirm today's 3 demo signals are prepared.
- [ ] Confirm the normal user DB was not reset.

- [ ] Run:

  ```powershell
  python run.py companion
  ```

- [ ] Companion window opens.
- [ ] Browser opens `/app#today`.
- [ ] Companion explains itself as a local helper.
- [ ] `오늘의 신호 열기` opens `/app#today`.
- [ ] `설정 화면 열기` opens `/app#settings`.
- [ ] `활동 기록 보기` opens `/app#activity`.

### First-Run Screen

- [ ] `시작하기` CTA is visible.
- [ ] Copy explains that LUMOS does not know the user's interests yet.
- [ ] No internal terms are visible.
- [ ] User can proceed without visiting settings first.

### Onboarding

- [ ] Step 1 role selection works.
- [ ] Step 2 keyword tag input works with comma or enter.
- [ ] At least three demo keywords can be added.
- [ ] Step 3 default count is 3.
- [ ] Briefing time default is visible.
- [ ] Generation mode labels are user-facing: 안정/혼합/실제 소스 모드.
- [ ] Privacy copy is visible and not alarming.
- [ ] `오늘의 신호 받기` is clear.

### Signal Generation

- [ ] Button enters disabled/busy state.
- [ ] Success toast appears.
- [ ] Today tab shows 3 signal cards.
- [ ] Cards show Korean display title and summary.
- [ ] Cards show `왜 중요한가`.
- [ ] Cards show `왜 나에게 추천됐나요?`.
- [ ] Cards show `다음에 볼 것`.

### Signal Details

- [ ] Details are closed by default.
- [ ] `자세히 보기` opens.
- [ ] Original title is preserved.
- [ ] Original snippet is preserved.
- [ ] Internal raw JSON is not visible by default.
- [ ] Source warning copy is soft and not alarming.

### Feedback

- [ ] `저장` shows friendly feedback.
- [ ] `관심 없음` shows friendly feedback.
- [ ] `계속 추적` shows friendly feedback.
- [ ] `원문 보기` opens original source or shows understandable fallback.
- [ ] No English traceback appears.

### Other Tabs

- [ ] `내 관심사` tab loads.
- [ ] Importance is shown as 높음/보통/낮음, not raw weight.
- [ ] `소스` tab loads.
- [ ] RSS URL input does not require JSON.
- [ ] `활동` tab loads.
- [ ] Raw JSON is hidden inside details.
- [ ] `설정` tab loads.
- [ ] First user is not overwhelmed by settings.

## Fallback Checklist

If Companion fails:

- [ ] Run `python run.py app`.
- [ ] Manually open `http://127.0.0.1:8000/app#today`.

If browser does not open:

- [ ] Paste URL manually.

If generation fails:

- [ ] Switch to 안정 모드.
- [ ] Use mock/stable data.
- [ ] Or restart with `python run.py demo-companion`.
- [ ] Explain this is a local MVP and external sources can be unstable.

If onboarding state is messy:

- [ ] Use clean DB or prepared demo DB.
- [ ] Restart app.

If deep link fails:

- [ ] Click the tab directly in Web UI.
- [ ] Continue demo from the active tab.

## Presentation-Ready Check

- [ ] One Korean signal card can be explained in under 30 seconds.
- [ ] One details panel can show original source preservation.
- [ ] One feedback action can be clicked.
- [ ] Screenshot checklist has either been completed or explicitly deferred.
- [ ] Fallback path is ready: stable/mock mode or `python run.py app`.
- [ ] The final message is ready:

  ```text
  LUMOS는 더 많은 정보를 보여주는 앱이 아니라, 오늘 봐야 할 신호만 줄이는 앱입니다.
  ```

# Demo Flow

Date: 2026-06-30

## Demo Purpose

This demo should make three things clear:

- LUMOS is not a generic news summary app.
- LUMOS chooses the few signals worth seeing today based on the user's interests and recent context.
- English source material can still be read as a Korean briefing, with the original source preserved in details.

Core message:

```text
LUMOS는 더 많은 정보를 보여주는 앱이 아니라, 오늘 봐야 할 신호만 줄여주는 개인 브리핑 앱입니다.
```

## Demo Preparation

General MVP run:

```powershell
python run.py companion
```

Stable demo run:

```powershell
python run.py demo-reset
python run.py demo-seed
python run.py demo-companion
```

Presenter note:

```text
지금은 발표 안정성을 위해 분리된 데모 DB로 실행하고 있습니다. 실제 사용 시에는 사용자의 온보딩과 관심사에 따라 신호가 생성됩니다.
```

Before running a live demo, also check:

- `docs/demo/manual_demo_checklist.md`
- `docs/demo/screenshots/README.md`
- latest rehearsal result in `docs/demo/demo_rehearsal_report.md`

Recommended state:

- Use a clean DB or prepared demo DB.
- Keep default sources seeded.
- Use `hybrid` when network is stable.
- Use `mock` or stable mode when network is unreliable.
- Keep the browser viewport at 1366x768 or 1440x900.
- Browser zoom: 90-100%.

Pre-check:

- Companion window opens.
- Browser opens `/app#today`.
- First-run CTA is visible if using a clean state.
- Signal generation succeeds.
- Signal cards show Korean display fields.
- Details preserve original title/snippet.
- `설정 화면 열기` opens `/app#settings`.
- `활동 기록 보기` opens `/app#activity`.

## 3-Minute Demo Scenario

### 0:00-0:20 Open

1. Run:

   ```powershell
   python run.py companion
   ```

2. Say:

   ```text
   LUMOS Companion은 메인 앱이 아니라 로컬 실행 도우미입니다. 오늘의 신호는 브라우저에서 확인합니다.
   ```

3. Click `오늘의 신호 열기`.

### 0:20-0:50 First Run

1. On the first-run screen, point to `시작하기`.
2. Say:

   ```text
   처음에는 사용자의 관심 기준을 30초 정도만 입력합니다. 설정을 먼저 뒤지지 않아도 바로 시작할 수 있게 만들었습니다.
   ```

3. Click `시작하기`.

### 0:50-1:30 Onboarding

Step 1:

- Select `예비 창업자 / PM`.
- Say:

  ```text
  역할은 신호를 고르는 기준으로만 사용합니다.
  ```

Step 2:

- Add:
  - `AI agent`
  - `생산성 툴`
  - `스타트업`

Step 3:

- Keep default count: 3.
- Keep default time: 08:00.
- Use `혼합 모드` if network is stable.
- Use `안정 모드` for offline or presentation-safe demo.

Say:

```text
기본값으로도 바로 첫 브리핑을 받을 수 있게 했고, 개인 맥락은 사용자가 켠 경우에만 참고합니다.
```

Click `오늘의 신호 받기`.

### 1:30-2:30 Signal Cards

After signals are generated:

1. Show that card titles and summaries are Korean.
2. Explain one card using:
   - `왜 중요한가`
   - `왜 나에게 추천됐나요?`
   - `다음에 볼 것`
3. Open `자세히 보기`.
4. Show original title/snippet preserved as supporting information.
5. Click `계속 추적`.

Say:

```text
원문이 영어여도 사용자는 먼저 한국어 브리핑을 봅니다. 원문 제목과 snippet은 숨기지 않고 자세히 보기 안에 보관합니다.
```

### 2:30-3:00 Companion And Wrap

1. Return to Companion.
2. Point to `새 신호 준비하기`, `개인 맥락 동기화`, `설정 화면 열기`, `활동 기록 보기`.
3. Say:

   ```text
   Companion은 작은 컨트롤러이고, 실제 읽기와 설정은 Web UI에서 합니다. 최종적으로는 조용히 도착하는 데스크톱 브리핑 경험으로 확장할 수 있습니다.
   ```

Wrap:

```text
LUMOS는 검색을 더 많이 하게 만드는 앱이 아니라, 오늘 볼 신호만 줄여서 판단 시간을 줄이는 앱입니다.
```

## 1-Minute Compressed Demo

1. Run `python run.py companion`.
2. Click `오늘의 신호 열기`.
3. If clean state: click `시작하기`, select `예비 창업자 / PM`, add `AI agent`, `생산성 툴`, `스타트업`, click `오늘의 신호 받기`.
4. Show one Korean Signal card.
5. Open details and show original title/snippet.
6. Click `계속 추적`.
7. End with:

   ```text
   영어 원문 자료도 한국어 브리핑으로 바꾸고, 사용자의 피드백을 다음 추천에 반영합니다.
   ```

## Fallback Scenarios

Signal generation fails:

- Switch generation mode to `안정 모드`.
- Use mock/stable data.
- Re-run `오늘의 신호 받기`.

Internet sources fail:

- Say:

  ```text
  외부 소스가 불안정할 때도 안정 모드로 제품 흐름은 검증할 수 있습니다.
  ```

Companion does not open:

```powershell
python run.py app
```

Browser does not open automatically:

Open manually:

```text
http://127.0.0.1:8000/app#today
```

Deep link does not switch tabs:

- Click the target tab directly in Web UI.
- Confirm URL hash manually.

Onboarding state is messy:

- Use a clean DB or prepared demo DB.
- Restart the app.

Feedback action fails:

- Continue demo with the visible toast/error state.
- Explain that feedback loop is implemented but local API state may need refresh.

## Do Not Overclaim

Avoid saying:

- "AI가 알아서 다 해줍니다."
- "완벽한 자동화입니다."
- "모든 정보를 수집합니다."
- "실시간으로 모든 트렌드를 추적합니다."
- "상용 서비스가 이미 준비됐습니다."

Use instead:

- "오늘 볼 만한 신호를 줄여줍니다."
- "사용자의 관심 기준을 참고합니다."
- "영어 원문을 한국어 브리핑으로 먼저 보여줍니다."
- "현재는 로컬 MVP입니다."

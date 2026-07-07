# Demo Data Strategy

Date: 2026-06-30

## Goal

Reduce demo risk while keeping the experience honest. The demo should show the real MVP flow, but it should not depend on unstable network conditions or messy local state.

## Demo DB Path

Demo mode uses a separate database:

```text
data/demo_lumos.db
```

The normal local database remains unchanged. `demo-reset` only deletes and recreates the demo DB and its SQLite sidecar files.

## Demo Commands

Reset demo DB:

```powershell
python run.py demo-reset
```

Seed demo persona, settings, interests, sources, and today's signals:

```powershell
python run.py demo-seed
```

Run Web UI with demo DB:

```powershell
python run.py demo
```

Run Companion with demo DB:

```powershell
python run.py demo-companion
```

Recommended pre-demo sequence:

```powershell
python run.py demo-reset
python run.py demo-seed
python run.py demo-companion
```

If a normal LUMOS server is already running on port 8000, demo commands stop with a warning instead of accidentally showing the default DB as demo data.

## Recommended Demo Persona

Role:

```text
예비 창업자 / PM
```

Interests:

- AI agent
- 생산성 툴
- 스타트업
- GitHub 트렌드
- 공식 블로그 업데이트

Goals:

- 창업 아이템 검증
- 경쟁 서비스 탐색
- 기술 변화 감지
- 매일 볼 정보 줄이기

Why this persona works:

- Hacker News, GitHub, RSS sources naturally produce relevant examples.
- English source material makes Korean briefing value visible.
- The feedback actions are easy to explain.

## Clean DB Strategy

Use a clean local state when showing first-run onboarding.

Recommended for:

- first user test
- onboarding demo
- mentoring session focused on UX

Checklist:

- profile is empty
- active interests are empty
- today's signals are empty
- source defaults can be seeded

Do not delete a real development DB unless it is explicitly a disposable demo copy.

## Prepared Demo DB Strategy

Use a prepared demo DB when time is short or network is unreliable.

Recommended state:

- profile exists for `예비 창업자 / PM`
- at least 3 active interests exist
- 3-5 Korean briefing signals exist
- feedback actions can still be clicked
- source defaults are enabled

Recommended for:

- 1-minute demo
- live presentation
- screen recording
- environments with unstable internet

## Stable Mode / Mock Scenario

Use stable/mock mode when:

- internet connection is unreliable
- source APIs are rate limited
- live demo must finish within 3 minutes
- the goal is to validate UX, not collector quality

Presenter wording:

```text
외부 소스가 불안정할 수 있어서, 지금은 안정 모드로 동일한 제품 흐름을 보여드리겠습니다.
```

What this validates:

- first-run onboarding
- signal card layout
- Korean briefing display
- details/source preservation
- feedback actions

What this does not validate:

- real collector freshness
- source coverage
- ranking quality on live data

## Hybrid Mode Scenario

Use hybrid mode when:

- internet is stable
- a longer demo is available
- the audience wants to see real external source behavior

Presenter wording:

```text
혼합 모드는 가능한 실제 소스를 함께 사용하고, 불안정한 소스가 있어도 제품 흐름이 끊기지 않게 합니다.
```

Pre-check:

- generate once before demo
- confirm at least 3 cards appear
- confirm Korean display fields exist
- confirm details preserve original English title/snippet

## Internet Failure Response

If live sources fail:

1. Do not debug during demo.
2. Switch to stable/mock flow.
3. Say:

   ```text
   외부 소스 연결은 로컬 환경과 네트워크 상태의 영향을 받습니다. 오늘은 안정 모드로 핵심 사용자 경험을 보여드리겠습니다.
   ```

4. Continue with onboarding, Korean cards, details, and feedback.

## Recommended Keyword Sets

### Startup / PM

- AI agent
- 생산성 툴
- 스타트업
- GitHub 트렌드
- 공식 블로그 업데이트

### Research / Graduate Student

- AI agent
- 논문 자동화
- 연구 도구
- arXiv
- 개발 생산성

### Content Planner

- 생성형 AI
- 크리에이터 도구
- 숏폼 트렌드
- 커뮤니티 반응
- 제품 출시

### Developer

- GitHub 트렌드
- developer tools
- API
- workflow automation
- open source

## Demo Data Quality Checklist

Before using a prepared demo DB:

- [ ] At least one card mentions a clear market/product/technology movement.
- [ ] Korean title is understandable without reading original source.
- [ ] Summary is 1-3 sentences.
- [ ] `왜 중요한가` is not generic.
- [ ] `왜 나에게 추천됐나요?` references interests.
- [ ] `다음에 볼 것` suggests a concrete next action.
- [ ] Original title/snippet exists in details.
- [ ] Source URL exists for at least one card.

## Data Handling Note

For user tests, avoid using a participant's real browser history or local folders unless they explicitly opt in. The first test should usually use manual keywords or prepared demo data.

# LUMOS

LUMOS는 오늘 봐야 할 신호만 조용히 골라주는 로컬 개인 브리핑 MVP입니다. 관심사, 최근 맥락, 선택한 외부 소스를 바탕으로 매일 확인할 만한 변화를 한국어 브리핑으로 정리합니다.

## 가장 쉬운 실행 방법

```powershell
python run.py companion
```

LUMOS Companion이 열리면:

1. `오늘의 신호 열기`로 브라우저의 Web UI를 엽니다.
2. 처음이라면 Web UI에서 `시작하기`를 눌러 온보딩을 진행합니다.
3. 역할과 관심사를 입력합니다.
4. `오늘의 신호 받기`로 첫 브리핑을 만듭니다.
5. 이후 Companion에서 `새 신호 준비하기`, `개인 맥락 동기화`, `설정 화면 열기`를 빠르게 실행할 수 있습니다.

Companion은 메인 화면이 아닙니다. 메인 사용자 화면은 브라우저에서 열리는 `/app` Web UI입니다. Companion은 LUMOS를 실행하고 Web UI로 연결해주는 작은 로컬 도우미이자 컨트롤러입니다. 현재는 정식 설치 앱, tray 앱, 백그라운드 서비스가 아니라 로컬 MVP용 실행 helper입니다.

정식 제품 단계에서는 Companion 창이 더 작아지거나 tray/background/notification 중심으로 축소될 수 있습니다.

## Companion 버튼이 여는 화면

- `오늘의 신호 열기` -> `http://127.0.0.1:8000/app#today`
- `새 신호 준비하기` -> 새 신호를 만든 뒤 `http://127.0.0.1:8000/app#today`
- `설정 화면 열기` -> `http://127.0.0.1:8000/app#settings`
- `활동 기록 보기` -> `http://127.0.0.1:8000/app#activity`
- `도움말` -> 이 README
- `Companion 닫기` -> Companion 창을 닫습니다.

Companion을 닫아도 이미 따로 실행 중이던 LUMOS 서버는 종료하지 않습니다. Companion이 직접 시작한 로컬 실행은 닫을 때 정리될 수 있습니다.

버튼을 눌렀는데 같은 화면처럼 보이면 브라우저 주소 끝의 hash가 `#settings`, `#activity`, `#today`처럼 바뀌었는지 확인하세요. 이미 열린 `/app` 화면에서도 hash가 바뀌면 해당 탭으로 전환되어야 합니다.

## Web UI만 직접 열기

```powershell
python run.py app
```

실행하면 FastAPI 서버가 켜지고 가능하면 브라우저가 자동으로 열립니다.

```text
http://127.0.0.1:8000/app
```

지원하는 직접 링크:

- `/app#today`
- `/app#signals`
- `/app#interests`
- `/app#sources`
- `/app#activity`
- `/app#settings`

## 안정 데모 모드

발표/멘토링에서는 인터넷 상태나 기존 DB 상태에 흔들리지 않도록 분리된 데모 DB를 사용할 수 있습니다.

데모 DB 경로:

```text
data/demo_lumos.db
```

기본 사용자 DB와 분리되어 있으며, `demo-reset`은 데모 DB만 초기화합니다.

발표 전 권장 순서:

```powershell
python run.py demo-reset
python run.py demo-seed
python run.py demo-companion
```

Web UI만 데모 DB로 실행:

```powershell
python run.py demo
```

각 명령의 역할:

- `demo-reset`: 데모 DB를 깨끗하게 초기화합니다.
- `demo-seed`: 예비 창업자 / PM persona, 관심사, 설정, source config, 오늘의 신호 3개를 준비합니다.
- `demo`: 데모 DB로 Web UI를 실행합니다.
- `demo-companion`: 데모 DB로 Companion과 Web UI를 실행합니다.

일반 사용성 검증은 여전히 clean DB 또는 `python run.py companion` 흐름으로도 확인해야 합니다. 데모 모드는 발표 안정성을 위한 로컬 실행 모드이며, 정식 배포 기능은 아닙니다.

## 처음 사용하는 흐름

1. 브라우저에서 LUMOS를 엽니다.
2. `시작하기`를 누릅니다.
3. 어떤 일을 하는지 선택합니다.
4. 요즘 보고 싶은 관심 키워드를 입력합니다.
5. 받을 신호 개수, 브리핑 시간, 생성 방식을 확인합니다.
6. `오늘의 신호 받기`를 누릅니다.
7. 영어 원문 기반 자료도 한국어 브리핑 카드로 확인합니다.
8. `저장`, `관심 없음`, `계속 추적`으로 다음 추천을 개선합니다.

## 주요 화면

- `오늘의 신호`: 한국어 제목, 요약, 추천 이유, 다음 행동을 확인합니다.
- `내 관심사`: LUMOS가 참고하는 관심 기준을 보고 숨기기, 다시 사용, 삭제, 중요도 조정을 할 수 있습니다.
- `소스`: Hacker News, GitHub, RSS 같은 외부 변화 확인 위치를 켜고 끕니다.
- `활동`: 오늘의 신호 생성, 개인 맥락 동기화, 피드백 기록을 확인합니다.
- `설정`: 받을 신호 개수, 브리핑 시간, 개인 맥락, 생성 방식을 조정합니다.

영어 원문 제목, snippet, URL은 숨기지 않고 Signal 카드의 `자세히 보기`와 `원문 보기`에 보관합니다. 기본 카드에서는 한국어 브리핑을 먼저 보여줍니다.

## 개발자용 명령

Companion 실행:

```powershell
python run.py companion
```

API만 실행:

```powershell
python run.py api
```

개발용 cloud auth skeleton 실행:

```powershell
python run.py cloud
```

Web UI 직접 실행:

```powershell
python run.py app
```

기존 tkinter UI 실행:

```powershell
python run.py desktop
```

기존 tkinter UI는 Companion과 별개입니다. `desktop`, `briefing`, `settings` 명령은 fallback/debug와 빠른 로컬 테스트 용도로 유지합니다.

브리핑 창만 열기:

```powershell
python run.py briefing
python run.py briefing --generate
```

설정 창만 열기:

```powershell
python run.py settings
```

스케줄러를 한 번만 실행:

```powershell
python run.py scheduler-once
python run.py scheduler-once --force
```

스모크 테스트:

```powershell
python tests/smoke_test.py
```

## 브라우저 QA 방법

권장 viewport:

- 1440x900
- 1366x768
- 1280x800
- 390x844

확인 흐름:

1. `python run.py companion` 실행
2. Companion에서 `오늘의 신호 열기` 클릭
3. First-run 화면과 `시작하기` CTA 확인
4. 온보딩 Step 1, Step 2, Step 3 진행
5. `오늘의 신호 받기` 클릭
6. 한국어 Signal 카드 3개 표시 확인
7. Signal 카드의 `자세히 보기`를 열어 원문 제목과 snippet 확인
8. `설정 화면 열기`, `활동 기록 보기`가 각각 `/app#settings`, `/app#activity`로 이동하는지 확인
9. `저장`, `관심 없음`, `계속 추적`, `원문 보기` 액션 확인

QA 기록:

- `docs/qa/mvp_reality_check.md`
- `docs/qa/korean_briefing_quality.md`
- `docs/qa/desktop_companion_mvp.md`

## 현재 범위

현재 제품 경로는 Web UI가 우선입니다. 기존 tkinter UI는 fallback, debug, 빠른 로컬 테스트 용도로 유지합니다.

유지되는 엔진 범위:

- API `/api/v1/*`
- signal pipeline
- RSS, Hacker News, GitHub collectors
- source config
- personal context sync
- interest control
- scheduler
- desktop tkinter UI
- settings window
- briefing window

## 알려진 한계

- 한국어 브리핑은 현재 rule-based 요약입니다. 완전한 번역기나 외부 LLM 요약기는 아닙니다.
- 일부 고유명사 중심 신호는 제목이 다소 넓게 보일 수 있습니다.
- 브라우저 기록과 로컬 파일은 사용자가 켠 경우에만 사용합니다.
- native tray/startup, 로그인, 결제, 배포 패키지는 아직 범위 밖입니다.
- Companion은 installer, auto-update, code signing을 제공하지 않습니다.
- Companion은 Web UI를 대체하지 않습니다.

## 데모와 사용자 테스트

발표, 멘토링, 사용자 테스트 전에는 아래 문서를 먼저 확인합니다.

- 데모 흐름: `docs/demo/demo_flow.md`
- 발표 스크립트: `docs/demo/pitch_demo_script.md`
- 사용자 테스트 시나리오: `docs/demo/user_test_script.md`
- 수동 데모 체크리스트: `docs/demo/manual_demo_checklist.md`
- 데모 데이터 전략: `docs/demo/demo_data_strategy.md`
- 사용자 반응 기반 다음 우선순위: `docs/demo/next_priorities_after_user_test.md`
- 데모 리허설 보고서: `docs/demo/demo_rehearsal_report.md`
- 스크린샷 QA 가이드: `docs/demo/screenshots/README.md`

데모 기본 실행:

```powershell
python run.py companion
```

데모에서 보여줄 핵심은 다음입니다.

- Companion은 메인 앱이 아니라 로컬 실행 도우미입니다.
- 메인 사용자 화면은 `/app` Web UI입니다.
- 처음 사용자는 `시작하기`로 온보딩을 진행합니다.
- 영어 원문 기반 자료도 한국어 브리핑 카드로 먼저 보여줍니다.
- `저장`, `관심 없음`, `계속 추적` 피드백이 다음 추천에 반영됩니다.

현재 MVP에는 정식 배포, 로그인, 결제, installer, auto-update, startup/tray 기능이 없습니다. 데모 중 외부 소스가 불안정하면 안정 모드 또는 mock 기반 흐름으로 전환해 핵심 UX를 검증합니다.

실제 발표 전에는 `docs/demo/manual_demo_checklist.md`를 따라 10분 사전 점검을 하고, 가능하면 `docs/demo/screenshots/README.md`의 화면 목록을 캡처합니다. 데모가 중간에 실패하면 `docs/demo/demo_flow.md`의 fallback 시나리오를 따릅니다.

## 상용 제품화 로드맵

현재 LUMOS는 local MVP입니다. 최종 목표는 실제 사용자가 가입하고, 다운로드하고, 로그인하고, 매일 쓰고, 요금제에 따라 결제할 수 있는 local + cloud hybrid subscription product입니다.

큰 단계:

1. Production architecture
2. Account/device auth
3. Entitlement/plan gate
4. Landing/download
5. Windows packaging
6. Closed beta
7. Billing
8. Operations/admin/telemetry

관련 문서:

- 제품화 아키텍처: `docs/product/production_readiness_architecture.md`
- 계정/기기/구독/권한 설계: `docs/product/account_device_subscription_design.md`
- Auth API contract: `docs/product/auth_api_contract.md`
- Local token storage policy: `docs/product/local_token_storage_policy.md`
- Auth UI wireframe: `docs/product/auth_ui_wireframe.md`
- Cloud/local 데이터 경계: `docs/product/cloud_local_split.md`
- 배포/패키징 계획: `docs/product/distribution_packaging_plan.md`
- 랜딩/가격/법무 계획: `docs/product/landing_pricing_legal_plan.md`
- 구현 로드맵: `docs/product/implementation_roadmap.md`

Account & Device Auth Foundation은 실제 로그인 구현이 아니라 auth boundary, API contract, token policy, mock auth client를 준비하는 단계입니다. 이번 단계에서도 실제 로그인, 회원가입, OAuth, 결제, installer, auto-update, code signing은 구현하지 않았습니다. 현재 로컬 MVP와 demo mode는 그대로 유지됩니다.

## 개발용 Cloud Auth Skeleton

Cloud Backend Minimal Auth Service 단계에서 local MVP와 분리된 개발용 cloud backend skeleton을 추가했습니다.

```powershell
python run.py cloud
```

기본 실행 주소:

```text
http://127.0.0.1:8010
```

Cloud DB 경로:

```text
data/cloud_lumos.db
```

구현된 개발용 endpoint:

- `GET /health`
- `POST /auth/dev-login`
- `POST /auth/logout`
- `POST /auth/refresh`
- `GET /auth/me`
- `POST /devices/register`
- `GET /devices`
- `GET /entitlements/me`
- `POST /usage/events`

주의:

- `/auth/dev-login`은 개발/계약 검증용입니다. 실제 회원가입, 비밀번호 로그인, OAuth, 이메일 인증이 아닙니다.
- token은 `dev_access_`, `dev_refresh_` prefix를 사용하며 production token이 아닙니다.
- Web UI와 Companion은 아직 cloud backend에 연결되지 않았고, 계속 `로컬 모드`로 사용할 수 있습니다.
- local DB `data/lumos.db`, demo DB `data/demo_lumos.db`, cloud DB `data/cloud_lumos.db`는 서로 분리되어 있습니다.
- QA 절차는 `docs/qa/cloud_auth_service_qa.md`에 정리되어 있습니다.

## 개발용 Local Cloud 연결 테스트

설정 탭의 `계정` 섹션에서 local app과 개발용 cloud backend 연결을 opt-in으로 확인할 수 있습니다.

권장 실행 순서:

```powershell
python run.py cloud
python run.py app
```

또는 Companion을 사용할 수 있습니다.

```powershell
python run.py cloud
python run.py companion
```

Web UI에서 `설정` 탭을 열고 `개발용 Cloud 연결 테스트`를 누르면 local app이 다음 흐름을 확인합니다.

1. cloud `/health`
2. cloud `/auth/dev-login`
3. cloud `/auth/me`
4. cloud `/devices/register`
5. cloud `/entitlements/me`

`사용량 이벤트 테스트`는 `dev_connection_test` 이벤트만 보냅니다. 브라우저 기록, 로컬 파일 원문, token, 민감한 URL은 보내지 않습니다.

이 기능은 상용 로그인 기능이 아닙니다. Cloud backend가 꺼져 있어도 LUMOS는 계속 로컬 모드로 사용할 수 있습니다. 자세한 QA 절차는 `docs/qa/local_cloud_dev_connection_qa.md`에 정리되어 있습니다.

개발용 local bridge endpoint는 `/api/v1/product/cloud/dev-connect` 등 `/api/v1/product/cloud/*` 아래에만 있습니다. production auth endpoint인 `/api/v1/auth/*`는 추가하지 않았습니다.

## Token Storage Prototype

현재 로그인은 아직 production 기능이 아닙니다. 다만 향후 실제 로그인으로 확장하기 위해 token storage abstraction을 추가했습니다.

- 기본 dev cloud 연결은 `memory-only`입니다.
- token은 Web UI, browser localStorage, sessionStorage에 저장하지 않습니다.
- refresh token을 SQLite나 일반 파일에 평문 저장하지 않는 것을 원칙으로 합니다.
- production 후보는 OS 보안 저장소입니다.
  - Windows: Credential Manager
  - macOS: Keychain
  - Linux: Secret Service/libsecret
- Python `keyring`이 사용 가능한 환경에서는 prototype으로 저장/조회/삭제를 검증할 수 있습니다.
- `LUMOS_DEV_PERSIST_TOKENS=1`을 명시한 경우에만 dev bridge가 OS 보안 저장소 prototype을 시도합니다.
- keyring이 없거나 실패하면 local mode와 dev bridge는 memory-only fallback으로 동작합니다.

관련 문서:

- `docs/product/local_token_storage_policy.md`
- `docs/qa/local_secure_token_storage_qa.md`

## Entitlement Cache & Offline Grace Prototype

현재 entitlement는 개발용 cloud 기반 prototype입니다. 실제 결제/구독 상태가 아니며, 기능 제한도 아직 적용하지 않습니다.

- Cloud에서 받은 Free / Pro / Team 권한 요약을 local app 메모리에 cache합니다.
- 기본 cache TTL은 24시간입니다.
- offline grace는 7일 정책 초안입니다.
- Cloud가 꺼져 있어도 local mode는 계속 사용할 수 있습니다.
- cache에는 token, 브라우저 기록, 로컬 파일 원문, 민감 URL을 저장하지 않습니다.
- grace가 만료되면 local mode 또는 Free-safe mode로 fallback하는 정책을 준비합니다.

관련 문서:

- `docs/product/entitlement_cache_offline_grace.md`
- `docs/qa/entitlement_cache_offline_grace_qa.md`

## Entitlement Gate Prototype

Free / Pro / Team 권한을 실제 LUMOS 기능과 연결하는 soft gate 구조를 추가했습니다.

- 현재는 안내만 표시합니다.
- 오늘의 신호 보기, 생성, 온보딩, 피드백, 설정 접근은 막지 않습니다.
- 실제 결제/구독 검증은 아직 연결되지 않았습니다.
- `GET /api/v1/product/gates/status`로 현재 gate summary를 확인할 수 있습니다.
- `POST /api/v1/product/gates/evaluate`로 특정 기능의 soft gate 판단을 확인할 수 있습니다.
- Web UI 설정 탭의 `요금제별 기능 안내`에서 현재 plan 기준 안내를 볼 수 있습니다.

관련 문서:

- `docs/product/entitlement_gate_policy.md`
- `docs/qa/entitlement_gate_integration_qa.md`

## Landing & Pricing Validation

판매 전 검증을 위해 `/app` 제품 UI와 분리된 landing/pricing preview를 추가했습니다.

실행:

```powershell
python run.py app
```

접근 경로:

- Landing: `http://127.0.0.1:8000/`
- Pricing: `http://127.0.0.1:8000/pricing`
- Download preview: `http://127.0.0.1:8000/download`
- Beta preview: `http://127.0.0.1:8000/beta`
- Product UI: `http://127.0.0.1:8000/app`

주의:

- 실제 결제는 아직 없습니다.
- 실제 회원가입/로그인은 아직 없습니다.
- 실제 이메일 수집 backend는 없습니다.
- 실제 installer/download 파일은 아직 없습니다.
- 현재 landing은 Free / Pro / Team 메시지와 월 9,900원 Pro 가격 가설을 검증하기 위한 preview입니다.

관련 문서:

- `docs/product/pricing_validation_plan.md`
- `docs/product/landing_copy.md`
- `docs/product/landing_pricing_legal_plan.md`

## Closed Beta & Download Readiness

현재 LUMOS는 closed beta 준비 단계입니다. 아직 실제 회원가입 backend, 이메일 수집 backend, 결제, installer, 일반 공개 다운로드 파일은 없습니다.

Closed beta preview:

- Beta page: `http://127.0.0.1:8000/beta`
- Download readiness: `http://127.0.0.1:8000/download`
- Pricing validation: `http://127.0.0.1:8000/pricing`

운영 방식:

- 베타 신청은 `/beta`의 신청 질문 템플릿을 복사해 이메일로 보내는 수동 모집 방식입니다.
- 외부 form SaaS나 이메일 수집 backend는 연결하지 않았습니다.
- `/download`는 실제 다운로드 버튼을 제공하지 않고, Windows portable build 준비 상태를 설명합니다.
- 선정된 beta tester에게만 수동 배포하는 흐름을 우선 검토합니다.

관련 문서:

- Closed beta intake plan: `docs/product/closed_beta_intake_plan.md`
- Beta email templates: `docs/product/beta_email_templates.md`
- Download readiness checklist: `docs/product/download_readiness_checklist.md`
- Release notes template: `docs/product/release_notes_template.md`
- Known issues template: `docs/product/known_issues_template.md`
- Beta feedback tracker: `docs/product/beta_feedback_tracker.md`
- QA checklist: `docs/qa/closed_beta_intake_download_readiness_qa.md`

다음 큰 구현 후보는 Windows Portable Build Prototype입니다. 이 단계 전에는 `docs/product/download_readiness_checklist.md`의 배포 전 smoke checklist를 통과해야 합니다.

## Windows Portable Build Prototype

Closed beta 사용자에게 Python 설치 없이 전달할 수 있는 Windows portable build 구조를 준비했습니다. 아직 정식 installer, code signing, auto-update, OS startup/tray는 없습니다.

권장 packaging 방식:

- PyInstaller `onedir`
- executable 이름: `LUMOS`
- entrypoint: `src/app/portable_entry.py`
- beta package 문서 포함
- 공개 다운로드가 아닌 closed beta 수동 배포용 zip

Build 관련 파일:

- `packaging/windows/build_portable.ps1`
- `packaging/windows/build_portable.py`
- `packaging/windows/lumos_portable.spec`
- `packaging/windows/README.md`
- `packaging/windows/beta_package/README_FIRST.md`
- `packaging/windows/beta_package/RELEASE_NOTES.md`
- `packaging/windows/beta_package/KNOWN_ISSUES.md`
- `packaging/windows/beta_package/PRIVACY_NOTES.md`
- `packaging/windows/beta_package/FEEDBACK_GUIDE.md`

Windows build:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build_portable.ps1
```

PyInstaller가 설치되어 있지 않으면 build script는 설치 안내를 출력하고 중단합니다.

이번 QA에서 확인된 artifact:

```text
dist/LUMOS/
dist/LUMOS-0.1.0-alpha-portable.zip
```

현재 artifact는 내부 closed beta QA용입니다. `/download` route로 공개 제공하지 않습니다.

Portable prototype data 위치:

```text
<LUMOS.exe가 있는 폴더>/data/
```

`LUMOS_DATA_DIR`로 data root를 override할 수 있고, 기존 `LUMOS_DB_PATH`도 유지됩니다. Beta build 기본 DB는 `data/lumos.db`이며, demo DB와 cloud DB는 별도로 유지합니다.

관련 문서:

- `docs/product/windows_portable_build_plan.md`
- `docs/qa/windows_portable_build_qa.md`

## Closed Beta Portable Manual QA

Windows portable artifact는 생성되었고 packaged runtime 기준 route, generate, feedback, persistence는 확인했습니다.

현재 readiness:

- 판단: Almost ready
- artifact: `dist/LUMOS/`, `dist/LUMOS-0.1.0-alpha-portable.zip`
- 대상: 일반 공개 다운로드가 아닌 closed beta 수동 전달
- local mode: Cloud backend 없이 사용 가능

이번 수동 QA에서 반영한 것:

- Companion UI 한국어 문구 정리
- beta package 문서 한국어 문구 정리
- 브라우저가 자동으로 열리지 않을 때 직접 접속 URL 안내
- `data/` 폴더 위치와 삭제 방법 안내
- code signing 전 단계의 SmartScreen/antivirus 경고 가능성 안내

남은 beta blocker:

- Python이 없는 clean Windows 10/11 환경 실행 확인
- visible Companion 화면 캡처
- 실제 브라우저 클릭 기반 onboarding/generate/feedback QA
- Windows SmartScreen/antivirus/firewall 경고 기록

관련 문서:

- `docs/qa/closed_beta_portable_manual_qa.md`

## Closed Beta Cohort 1 Launch Readiness

Cohort 1 발송 전 최종 readiness gate를 정리했습니다.

현재 판단:

- 판단: Almost ready
- 테스트 artifact: `dist/LUMOS-0.1.0-alpha-portable.zip`
- SHA256: `2074F5780806D71703D6A5D581A5708B10A41A1C1479EF60C021D143621084C5`
- size: `28,659,565 bytes`
- 상태: 개발 Windows 환경에서는 packaged app 실행, route, generate, feedback, persistence 통과

남은 blocker:

- Python이 없는 clean Windows 10/11 환경 실행 확인
- SmartScreen / antivirus / firewall 경고 실제 캡처
- 실제 사용자처럼 클릭 기반 onboarding 완료 확인
- DPI 100% / 125% / 150%에서 Companion 레이아웃 확인

운영 문서:

- Cohort 1 launch pack: `docs/product/cohort1_launch_pack.md`
- Launch readiness QA: `docs/qa/closed_beta_cohort1_launch_readiness.md`
- Beta email templates: `docs/product/beta_email_templates.md`
- Feedback tracker: `docs/product/beta_feedback_tracker.md`

현재 artifact는 아직 일반 공개 다운로드가 아니며, Cohort 1 선정자에게만 수동 전달하는 closed beta 후보입니다.

## Closed Beta Cohort 1 Canary Run

현재 다음 단계는 Cohort 1 전체 발송이 아니라 canary tester 1명에게 먼저 전달하는 단계입니다.

Canary 목적:

- Python 없는 일반 Windows 환경에서 `LUMOS.exe` 실행 확인
- SmartScreen / Defender / antivirus / firewall 경고 수집
- Companion visible 확인
- 브라우저 `/app` 열림 확인
- onboarding → signal 3개 생성 → feedback 클릭 확인
- 종료 후 재실행과 persistence 확인

Canary artifact:

- `dist/LUMOS-0.1.0-alpha-portable.zip`
- SHA256: `2074F5780806D71703D6A5D581A5708B10A41A1C1479EF60C021D143621084C5`

운영 문서:

- Canary checklist: `docs/product/canary_run_checklist.md`
- Canary feedback form: `docs/product/canary_feedback_form.md`
- Canary QA template: `docs/qa/cohort1_canary_run.md`
- Cohort 1 launch pack: `docs/product/cohort1_launch_pack.md`

실제 canary tester에게 전송하는 행위는 수동 운영 절차입니다. 이 repo에는 public download route나 이메일 발송 backend를 추가하지 않았습니다.

Canary result review 상태:

- 실제 canary tester 결과: 아직 제공되지 않음
- 현재 판단: pending
- Cohort 1 3~5명 확장: 아직 승인하지 않음
- 결과 기록 문서: `docs/qa/cohort1_canary_run.md`

`pass_to_cohort1`, `fix_before_cohort1`, `stop_release` 판단은 실제 canary 결과를 받은 뒤에만 기록합니다.

## 계정 상태

현재 LUMOS는 로그인 없이 `로컬 모드`로 사용할 수 있습니다.

- 계정/로그인/구독은 아직 실제 Cloud Backend와 연결되지 않았습니다.
- 설정 탭의 `계정` 섹션에서 현재 로컬 모드 상태를 확인할 수 있습니다.
- Companion에서도 `계정: 로컬 모드`가 표시됩니다.
- `?mockAuth=free` 또는 `?mockAuth=pro` 표시는 개발/QA용 mock 상태일 뿐 실제 로그인이나 구독이 아닙니다.
- 이후 Cloud Backend가 준비되면 계정, 기기 등록, 구독 상태, entitlement 확인과 연결할 예정입니다.

현재 단계에서는 Web UI를 login-required로 만들지 않습니다. 기존 로컬 MVP 사용 흐름은 그대로 유지됩니다.

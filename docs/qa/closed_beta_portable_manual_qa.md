# Closed Beta Portable Manual QA

Phase: Closed Beta Portable Manual QA Pass  
Date: 2026-07-07  
App version: 0.1.0-alpha  
Artifact: `dist/LUMOS-0.1.0-alpha-portable.zip`

## Purpose

Closed beta Cohort 1 사용자에게 Windows portable zip을 수동 전달하기 전에, 실제 사용자 관점에서 압축 해제, `LUMOS.exe` 실행, Companion, 브라우저, 온보딩, 오늘의 신호, feedback, 데이터 보존, 보안 경고 안내를 확인한다.

## QA Environment

현재 수행 환경:

- OS: Windows 개발 머신
- Python: 설치되어 있음
- 기존 LUMOS 개발 환경: 있음
- 네트워크: 연결됨
- 실행 artifact: `dist/LUMOS-0.1.0-alpha-portable.zip`
- 실행 폴더: `dist/LUMOS/`
- Cloud backend: 실행하지 않음
- Local mode: 유지

아직 수행하지 못한 환경:

- Python이 설치되지 않은 clean Windows 10/11 환경
- 개발 repo가 없는 완전 신규 사용자 환경
- Windows Defender/SmartScreen 경고 전체 캡처

## Artifact Record

문구 수정 후 재빌드한 artifact:

- `dist/LUMOS-0.1.0-alpha-portable.zip`
- Size: 28,659,565 bytes
- SHA256: `2074F5780806D71703D6A5D581A5708B10A41A1C1479EF60C021D143621084C5`
- `dist/LUMOS/LUMOS.exe`
- Size: 10,382,488 bytes

## Zip Extraction QA

결과: Pass

확인한 항목:

- zip 구조에 `LUMOS.exe`가 포함됨
- beta package 문서가 포함됨
- `.db`, `.db-wal`, `.db-shm` 미포함
- `.env` 미포함
- token/cache/log 파일 미포함
- local personal DB 미포함
- `tkinter/test`와 tkinter `__pycache__` packaging noise 제거

발견한 문제:

- beta package 문서 일부와 Companion UI 문구가 인코딩 깨짐 상태였다.

수정:

- `README_FIRST.md`, `RELEASE_NOTES.md`, `KNOWN_ISSUES.md`, `PRIVACY_NOTES.md`, `FEEDBACK_GUIDE.md`를 정상 한국어 문구로 교체했다.
- Companion 사용자 문구를 정상 한국어로 교체했다.
- 수정 후 `dist/LUMOS-0.1.0-alpha-portable.zip`을 다시 생성했다.

## Visible Companion QA

결과: Pass on current development Windows machine

확인:

- `LUMOS.exe` 실행 시 `LUMOS Companion` 창 handle이 생성됨
- Companion 창 title 확인됨
- `/health` 응답 확인됨
- Companion 창이 screenshot에서 전면에 표시됨
- Companion 한글 문구 정상 표시 확인
- `/app#today`가 브라우저에서 열림

수정:

- Companion 창을 실행 직후 전면으로 올리는 최소 처리 추가
- Companion title, subtitle, status, button, 안내 문구를 정상 한국어로 교체

필요한 추가 확인:

- DPI scaling 100%/125%에서 버튼이 잘리지 않는지 확인

## Browser Open QA

결과: Pass on current development Windows machine

확인:

- packaged app 실행 상태에서 `/health` 응답 200
- packaged app에서 `/app`, `/`, `/pricing`, `/download`, `/beta`, `/static/app.js`, `/landing-static/landing.js` 모두 200
- Companion deep link는 `/app#today`를 사용
- screenshot에서 브라우저가 `http://127.0.0.1:8000/app#today`로 열린 것 확인

남은 확인:

- clean 사용자 환경에서 기본 브라우저가 실제로 `/app#today`를 전면에 여는지 확인
- 브라우저가 열리지 않을 때 `README_FIRST.md`의 직접 접속 URL 안내가 충분한지 확인

## Onboarding QA

결과: Product API flow pass, manual click QA remains

현재 packaged QA에서 확인:

- clean data directory 기반 first-run 상태 확인
- 오늘의 신호 생성 API로 3개 signal 생성
- 한국어 briefing field 표시 가능 상태 확인

남은 확인:

- 실제 브라우저 클릭으로 `시작하기`부터 Step 1/2/3 진행
- loading 상태와 오류 메시지 확인
- 버튼과 입력 필드가 1366x768 화면에서 잘리지 않는지 확인

## Product Flow QA

결과: Product API flow pass, manual click QA remains

현재 packaged QA에서 확인:

- generate 정상
- today signals count 3
- feedback `saved` 저장 정상
- persistence 정상
- Cloud backend 없이 local mode 유지

남은 확인:

- details 펼침 상태 시각 확인
- `저장`, `관심 없음`, `계속 추적` 버튼 직접 클릭
- 내 관심사, 소스, 활동, 설정 탭 직접 이동
- 계정 shell과 soft gate 안내가 production login/결제처럼 보이지 않는지 확인

## Data Persistence QA

결과: Pass in packaged runtime test

확인:

- 지정 data directory에서 `lumos.db` 생성
- 앱 종료 후 재실행해도 signals 유지
- feedback event 유지
- Cloud backend 없이 local mode 유지
- 재실행 후 `today signals = 3` 확인

문서 보완:

- `README_FIRST.md`와 `PRIVACY_NOTES.md`에 `data/` 위치와 삭제 방법을 명확히 추가했다.

## Close / Reopen / Port Conflict QA

결과: Partial pass

확인:

- Companion close/reopen 흐름은 packaged runtime에서 재실행 가능
- 같은 `LUMOS_DATA_DIR`로 재실행 시 data persistence 유지

남은 확인:

- clean 사용자 환경에서 Companion 닫기 후 프로세스 잔류 여부
- 포트 `8000`이 다른 프로세스에 점유된 상태의 사용자 안내
- 브라우저 탭이 남아 있을 때 재실행 UX

## SmartScreen / Antivirus / Firewall

결과: Not fully verified

현재 확인:

- 이번 환경에서는 Windows SmartScreen/antivirus 경고를 완전하게 캡처하지 못했다.
- code signing이 없으므로 경고 가능성은 known issue로 문서화했다.

문서 보완:

- `KNOWN_ISSUES.md`와 `README_FIRST.md`에 보안 경고 가능성과 주의 문구를 추가했다.
- “무시하고 실행”을 강하게 안내하지 않고, 의심스러우면 실행하지 말고 문의하도록 작성했다.

남은 확인:

- clean Windows 10/11 환경에서 SmartScreen/Defender/방화벽 경고 실제 캡처
- `docs/demo/screenshots/closed_beta/10_security_warning_if_any.png` 생성 여부 확인

## Screenshot Record

현재 생성:

- `docs/demo/screenshots/closed_beta/02_companion_visible.png`

확인:

- Companion visible UI와 `/app#today` 브라우저 화면이 함께 캡처됨

권장 추가 screenshot:

- `01_unzipped_folder.png`
- `02_companion_visible.png`
- `03_browser_today_first_run.png`
- `04_onboarding_step_1.png`
- `05_onboarding_step_2.png`
- `06_onboarding_step_3.png`
- `07_today_signals.png`
- `08_signal_details.png`
- `09_settings_account_shell.png`
- `10_security_warning_if_any.png`

## Fixed Issues

- Companion UI 한국어 인코딩 깨짐 수정
- Companion 실행 직후 전면 표시 개선
- Help 버튼이 packaged beta 문서를 우선 열도록 수정
- beta package 문서 한국어 인코딩 깨짐 수정
- `/download` page 문구를 closed beta 수동 배포 상태에 맞게 정리
- `/beta` page 문구를 수동 신청 템플릿 중심으로 정리
- 보안 경고, 데이터 삭제, 직접 URL 접속 안내 보강

## Remaining Issues

- Python이 없는 clean Windows 환경에서 실행 확인 필요
- SmartScreen/antivirus/firewall 경고 실제 캡처 필요
- 실제 브라우저 클릭 기반 onboarding/product flow 확인 필요
- DPI scaling별 Companion visible UI 확인 필요
- 포트 충돌 상황 사용자 안내 확인 필요

## Beta Readiness

Judgment: Almost ready

이유:

- portable artifact 생성과 packaged route/product API flow는 통과했다.
- zip에 민감 파일이 포함되지 않는 것은 확인됐다.
- 사용자에게 보이는 치명적인 한국어 문구 깨짐은 수정했다.
- 다만 clean Windows 10/11, Python 미설치 환경, SmartScreen/antivirus 경고, 실제 클릭 기반 browser UX가 아직 완전 검증되지 않았다.

## Next Step

Closed Beta Cohort 1 Launch 전 마지막 blocker fix:

1. 문구 수정 반영 후 portable artifact 재빌드
2. clean Windows 10/11 또는 VM에서 zip 압축 해제 실행
3. `LUMOS.exe` visible Companion screenshot 확보
4. 브라우저 온보딩 수동 클릭 QA
5. SmartScreen/antivirus 경고 여부 기록

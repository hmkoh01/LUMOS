# Cohort 1 Launch Pack

## Goal

Closed beta Cohort 1은 LUMOS가 실제 사용자에게 설치, 첫 실행, 오늘의 신호 생성, feedback까지 전달될 수 있는지 확인하는 최소 운영 테스트다.

검증 목표:

- Windows portable zip을 외부 사용자에게 수동 전달할 수 있는가.
- 첫 사용자가 Companion과 Web UI의 역할을 이해하는가.
- 오늘의 신호 3개가 읽을 만한가.
- 한국어 briefing이 영어 source 부담을 줄이는가.
- local-first 개인정보 설명이 신뢰되는가.
- 월 9,900원 Pro 가격 가설에 반응이 있는가.

## Cohort Size

- 1차: 3~5명
- 2차 후보: 10명
- 3차 후보: 30명

Cohort 1은 기능 확장보다 설치/첫 실행/가치 이해를 검증한다.

## Canary Before Cohort 1

Cohort 1 전체 발송 전에 신뢰 가능한 canary tester 1명에게만 먼저 전달한다.

Canary tester 기준:

- 신뢰 가능한 지인 또는 초기 협력자 1명.
- Windows 10 또는 Windows 11 사용자.
- 가능하면 Python이 설치되어 있지 않은 환경.
- zip 압축 해제와 `LUMOS.exe` 실행이 가능한 사용자.
- 화면 캡처를 보내줄 수 있는 사용자.
- SmartScreen, Defender, antivirus, firewall 경고를 기록해줄 수 있는 사용자.
- 10~15분 정도 onboarding과 첫 사용을 해줄 수 있는 사용자.
- 오류가 나도 침착하게 피드백을 줄 수 있는 사용자.

Canary tester에게 기대하는 것:

1. zip 압축 해제.
2. `LUMOS.exe` 실행.
3. 보안 경고 여부 캡처.
4. Companion 창 확인.
5. 브라우저가 열리는지 확인.
6. onboarding 완료.
7. 오늘의 신호 생성.
8. feedback 버튼 클릭.
9. 종료 후 재실행.
10. 1차 사용 소감 전달.

Canary 결과 판단:

- `pass_to_cohort1`: 치명적 blocker 없이 Cohort 1 3~5명으로 확장 가능.
- `fix_before_cohort1`: 수정 후 canary를 한 번 더 실행해야 함.
- `stop_release`: 실행/보안/데이터 관련 중대한 문제가 있어 발송 중단.

Current canary review status:

- actual canary result: not received
- current decision: pending
- Cohort 1 3~5명 발송: not approved yet

Decision cannot be made until the canary tester provides Windows environment, security warning, onboarding, signal generation, feedback, and close/reopen results.

## Target Users

우선순위:

1. 예비 창업자
2. 1인 창업자
3. PM / Product Builder
4. AI/생산성 툴을 자주 보는 지식근로자
5. 스타트업/기술 트렌드를 계속 추적해야 하는 사람

High-fit signal:

- 매일 트렌드/AI/product 정보를 확인한다.
- 정보 탐색 시간이 부담이다.
- 영어 원문 피로가 있다.
- Windows 사용 가능하다.
- 피드백 인터뷰에 응할 수 있다.

## Artifact

- File: `LUMOS-0.1.0-alpha-portable.zip`
- Version: `0.1.0-alpha`
- SHA256: `2074F5780806D71703D6A5D581A5708B10A41A1C1479EF60C021D143621084C5`
- Size: `28,659,565 bytes`
- Distribution: selected closed beta users only

Do not publish this artifact through `/download`.

## Delivery Method

수동 전달:

1. 선정된 사용자에게 개별 연락.
2. zip 파일과 SHA256을 함께 전달.
3. `README_FIRST.md`, `KNOWN_ISSUES.md`, `PRIVACY_NOTES.md`를 먼저 읽도록 안내.
4. 실행이 불안하면 중단하고 문의하도록 안내.
5. 첫 실행 후 10분 이내 피드백 요청.

## First Email Summary

메일에는 다음을 포함한다.

- 파일명과 SHA256
- 압축 해제 방법
- `LUMOS.exe` 실행 방법
- 브라우저가 열리지 않을 때 직접 접속 URL: `http://127.0.0.1:8000/app`
- SmartScreen/antivirus 경고 가능성
- 신뢰할 수 있는 전달 경로로 받은 파일만 실행하라는 안내
- 오늘의 신호 3개 확인 요청
- 저장 / 관심 없음 / 계속 추적 중 하나 클릭 요청

전체 템플릿: `docs/product/beta_email_templates.md`

## Known Issues Summary

- 정식 installer 없음
- code signing 없음
- auto-update 없음
- OS startup/tray 없음
- production cloud login 없음
- 결제/요금제 관리 없음
- 일반 공개 다운로드 없음
- SmartScreen/antivirus 경고 가능성 있음

## Feedback Questions

첫 실행 직후:

- 실행이 쉬웠나요?
- Companion 역할을 이해했나요?
- 브라우저가 자연스럽게 열렸나요?
- 오늘의 신호가 무엇인지 바로 이해됐나요?
- 한국어 briefing이 자연스러웠나요?
- 저장 / 관심 없음 / 계속 추적의 차이가 명확했나요?

3일 후:

- 다시 열어봤나요?
- 오늘의 신호가 유용했나요?
- 불필요하거나 애매한 신호가 있었나요?
- 계속 쓰려면 무엇이 먼저 개선되어야 하나요?

7일 후:

- 계속 쓸 의향이 있나요?
- 월 9,900원 Pro에 지불 의향이 있나요?
- Pro에 꼭 필요한 기능은 무엇인가요?
- local-first 설명을 신뢰했나요?

## Success Criteria

Ready to continue if:

- 3명 이상 실행 성공.
- 2명 이상 첫 신호 생성 성공.
- 2명 이상 계속 써볼 의향 있음.
- 최소 1명 이상 월 9,900원 가격에 긍정 또는 조건부 긍정.
- 치명적 설치 blocker 없음.
- 개인정보/local-first 설명에 큰 불신 없음.

## Go / No-go Criteria

Go:

- clean Windows에서 실행 성공.
- SmartScreen/antivirus 안내가 준비됨.
- onboarding, generate, feedback이 사용자 클릭으로 통과.
- zip에 민감 파일 없음.
- 전달 메일과 feedback tracker 준비.

No-go:

- Python 없는 환경에서 실행 불가.
- Companion 창이 보이지 않거나 한글이 깨짐.
- `/app`이 열리지 않음.
- 오늘의 신호 생성 실패.
- feedback 저장 실패.
- 보안 경고 안내가 부족해 사용자가 불안해함.

## Metrics to Collect

- install success rate
- first-run completion rate
- signal generation success rate
- feedback click rate
- day 2 reopen
- day 3 reopen
- price reaction
- privacy reaction
- must-fix issue count
- participant quote

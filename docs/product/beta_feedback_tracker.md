# Beta Feedback Tracker

실명이나 민감한 개인정보 대신 participant id를 사용한다. 피드백에는 브라우저 기록, 로컬 파일 원문, 개인 문서 내용, 민감 URL을 기록하지 않는다.

## Tracker Table

| canary_id | participant_id | cohort | artifact_sha256 | persona | windows_version | python_installed | date_invited | unzip_success | exe_launch_success | install_status | install_notes | smartscreen_seen | defender_warning_seen | antivirus_warning | firewall_warning_seen | companion_visible | browser_opened | first_run_completed | onboarding_completed | signal_generated | signal_generated_count | feedback_clicked | feedback_saved | reopen_success | reopened_day2 | reopened_day3 | first_signal_reaction | repeated_use_intent | willingness_to_pay | price_reaction | privacy_reaction | blocker_level | bug_severity | must_fix_issue | must_fix_before_cohort1 | cohort1_ready | nice_to_have | quote | follow_up_needed | canary_decision | cohort_decision | next_action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CANARY-001 | P001 | C1-canary | 2074F5780806D71703D6A5D581A5708B10A41A1C1479EF60C021D143621084C5 | 예비 창업자 / PM | Windows 10/11 | Yes/No/Unknown | YYYY-MM-DD | Yes/No | Yes/No | Not sent / Sent / Installed / Failed |  | Yes/No | Yes/No | Yes/No | Yes/No | Yes/No | Yes/No | Yes/No | Yes/No | Yes/No | 0/1/2/3 | Yes/No | Yes/No | Yes/No | Yes/No | Yes/No | 좋음/보통/나쁨 | 높음/보통/낮음 | 높음/보통/낮음 | 긍정/조건부/부정 | 신뢰/보통/불신 | none/minor/major/critical | None/Low/Medium/High/Critical |  | Yes/No | Yes/No |  |  | Yes/No | pass_to_cohort1 / fix_before_cohort1 / stop_release | Keep / Wait / Drop |  |

## Field Guide

- `install_status`: zip 수신부터 실행 성공까지의 상태.
- `install_notes`: 압축 해제 위치, 실행 중 보인 메시지, 사용자 혼란 지점.
- `canary_id`: canary run 식별자.
- `artifact_sha256`: 전달한 zip의 SHA256.
- `windows_version`: 사용자의 Windows 버전.
- `python_installed`: Python 설치 여부.
- `unzip_success`: 압축 해제 성공 여부.
- `exe_launch_success`: `LUMOS.exe` 실행 성공 여부.
- `smartscreen_seen`: SmartScreen 경고를 봤는지.
- `defender_warning_seen`: Windows Defender 경고를 봤는지.
- `antivirus_warning`: Windows Defender 또는 antivirus 경고를 봤는지.
- `firewall_warning_seen`: firewall 허용 창을 봤는지.
- `companion_visible`: Companion 창이 보였는지.
- `browser_opened`: 브라우저가 자동으로 열렸는지.
- `first_run_completed`: 온보딩 완료 여부.
- `onboarding_completed`: 실제 클릭 기반 온보딩 완료 여부.
- `signal_generated`: 오늘의 신호 3개 생성 여부.
- `signal_generated_count`: 생성된 신호 수.
- `feedback_clicked`: 저장 / 관심 없음 / 계속 추적 중 하나를 눌렀는지.
- `feedback_saved`: feedback 저장이 성공한 것으로 보였는지.
- `reopen_success`: 종료 후 재실행 성공 여부.
- `reopened_day2`, `reopened_day3`: 다시 열어봤는지.
- `price_reaction`: 월 9,900원 Pro에 대한 반응.
- `privacy_reaction`: local-first 설명에 대한 신뢰도.
- `bug_severity`: Cohort 1 운영 관점의 심각도.
- `blocker_level`: release blocker 수준.
- `must_fix_before_cohort1`: Cohort 1 전체 발송 전에 반드시 수정해야 하는지.
- `cohort1_ready`: 이 사용자 결과만 기준으로 Cohort 1 확장이 가능한지.
- `canary_decision`: canary 이후 판단. `pass_to_cohort1`, `fix_before_cohort1`, `stop_release`.
- `cohort_decision`: 다음 cohort에 계속 포함할지 판단.

## 기록 원칙

- participant id만 사용한다.
- 연락처는 별도 안전한 운영 문서에서 관리한다.
- 민감한 개인 맥락은 기록하지 않는다.
- 인용은 제품 판단에 필요한 짧은 문장만 남긴다.
- 가격 피드백은 금액, 이유, 대체 도구를 함께 요약한다.

## Must-fix 분류

- Critical: 실행 불가, 데이터 손상, 보안상 오해를 크게 부르는 문제.
- High: first-run onboarding 막힘, 신호 생성 실패, feedback 저장 실패.
- Medium: Companion 역할 혼란, 카드 문구 이해 어려움, 가격/개인정보 설명 불충분.
- Low: 문구 어색함, 버튼 위치, 시각 밀도.

## Cohort 1 성공 기준

- 3명 이상 실행 성공.
- 2명 이상 첫 신호 생성 성공.
- 2명 이상 계속 써볼 의향 있음.
- 최소 1명 이상 월 9,900원 가격에 긍정 또는 조건부 긍정.
- 개인정보/local-first 설명에 큰 불신 없음.

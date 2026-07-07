# Canary Run Checklist

Closed Beta Cohort 1 전체 발송 전에 canary tester 1명에게만 먼저 전달하기 위한 체크리스트다.

## Artifact

- [ ] 최신 artifact 파일명 확인: `LUMOS-0.1.0-alpha-portable.zip`
- [ ] 최신 SHA256 확인: `2074F5780806D71703D6A5D581A5708B10A41A1C1479EF60C021D143621084C5`
- [ ] zip size 확인: `28,659,565 bytes`
- [ ] zip에 `.db`, `.env`, token/cache/log 포함 없음 확인
- [ ] public download route에 artifact 제공 없음 확인

## Canary Tester

- [ ] 신뢰 가능한 canary tester 1명 선정
- [ ] Windows 10/11 사용 여부 확인
- [ ] Python 미설치 환경이면 우선 선정
- [ ] 화면 캡처 가능 여부 확인
- [ ] 10~15분 테스트 가능 여부 확인
- [ ] 오류 발생 시 피드백 가능한지 확인

## Delivery

- [ ] canary email template 준비
- [ ] artifact 전달 경로 결정
- [ ] SHA256을 이메일에 포함
- [ ] SmartScreen/Defender 경고 가능성 안내
- [ ] 의심스러우면 실행하지 말라고 안내
- [ ] direct URL 안내: `http://127.0.0.1:8000/app`

## Tester Tasks

- [ ] zip 압축 해제
- [ ] `LUMOS.exe` 실행
- [ ] 보안 경고 캡처
- [ ] Companion 표시 확인
- [ ] 브라우저 자동 열림 확인
- [ ] onboarding 완료
- [ ] 오늘의 신호 3개 생성
- [ ] details 열기
- [ ] feedback 버튼 클릭
- [ ] 종료 후 재실행

## Collection

- [ ] Windows 버전 수집
- [ ] Python 설치 여부 수집
- [ ] SmartScreen/Defender/firewall 결과 수집
- [ ] Companion screenshot 수집
- [ ] onboarding 결과 수집
- [ ] signal/feedback 결과 수집
- [ ] 재실행 결과 수집
- [ ] canary feedback form 회수
- [ ] beta feedback tracker 업데이트

## Go / No-go

- [ ] `pass_to_cohort1`
- [ ] `fix_before_cohort1`
- [ ] `stop_release`

Decision rule:

- 실행 불가, 보안 경고 안내 부족, 데이터 문제, 신호 생성 실패는 Cohort 1 전체 발송 전 수정한다.
- 경미한 문구나 화면 밀도 문제는 tracker에 기록하고 Cohort 1에서 추가 확인할 수 있다.

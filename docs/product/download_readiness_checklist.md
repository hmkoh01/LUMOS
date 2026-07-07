# Download Readiness Checklist

## 현재 상태

- 아직 installer는 없다.
- 아직 일반 공개 다운로드는 없다.
- 현재는 Python local 실행 또는 향후 Windows portable build를 준비하는 단계다.
- closed beta 선정자에게만 수동 배포하는 흐름을 우선 검토한다.

## 외부 사용자 배포 전 필요한 것

- Windows portable build
- app version
- release notes
- known issues
- 실행 파일 이름
- 앱 아이콘
- 데이터 저장 위치 안내
- 로그 위치 안내
- 삭제 방법
- 보안/개인정보 안내
- 바이러스 오탐 가능성 안내
- 기본 실행 테스트
- demo DB가 아닌 일반 DB 확인
- crash/오류 수집 방법

## 첫 beta build 기준

- Windows 10/11에서 실행 가능
- Python 없이 실행 가능
- `LUMOS Companion` 실행 가능
- `/app` 자동 열림
- first-run onboarding 가능
- 오늘의 신호 생성 가능
- 설정/계정 shell 정상 표시
- local mode 정상
- cloud backend가 없어도 앱 기본 사용 가능
- cloud dev 기능은 beta에서 숨기거나 개발 안내로만 유지

## 배포 패키지 구성 후보

- `LUMOS.exe`
- `README_FIRST.md`
- `RELEASE_NOTES.md`
- `KNOWN_ISSUES.md`
- `PRIVACY_NOTES.md`

## 배포 전 smoke checklist

- 실행 파일 실행
- Companion 창 표시
- 브라우저에서 `/app#today` 열림
- first-run onboarding 진행
- 오늘의 신호 생성
- 한국어 briefing card 표시
- 저장/관심 없음/계속 추적 feedback 동작
- 설정 탭 접근
- 계정 shell이 local mode로 표시
- 앱 종료 후 재실행
- 데이터 유지 확인
- 삭제/데이터 제거 안내 확인

## 배포 금지 조건

- 실행 파일이 첫 화면에서 멈춘다.
- 오늘의 신호 생성이 반복적으로 실패한다.
- 오류가 traceback으로 노출된다.
- 개인정보/local-first 안내가 없다.
- demo DB가 beta build에 섞여 있다.
- 다운로드 페이지가 일반 공개 다운로드처럼 보인다.

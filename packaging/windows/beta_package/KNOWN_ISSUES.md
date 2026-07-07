# Known Issues

이 빌드는 closed beta용 alpha portable build입니다.

## 아직 포함되지 않은 것

- 정식 installer
- code signing
- auto-update
- OS startup 또는 tray 실행
- production cloud login
- 결제 또는 요금제 관리
- 일반 공개 다운로드
- 자동 오류 수집

## 실행 중 보일 수 있는 문제

- Windows SmartScreen 또는 antivirus 경고가 보일 수 있습니다.
- 일부 환경에서 브라우저가 자동으로 앞으로 나오지 않을 수 있습니다.
- 포트 `8000`을 다른 프로그램이 사용 중이면 LUMOS가 바로 열리지 않을 수 있습니다.
- 인터넷 상태에 따라 일부 source 기반 신호 품질이 달라질 수 있습니다.
- Cloud 연결 기능은 개발 확인용이며, beta 사용에 필수 기능이 아닙니다.

## 해결 방법

- 브라우저가 자동으로 열리지 않으면 `http://127.0.0.1:8000/app`을 직접 입력하세요.
- 보안 경고가 의심스럽다면 실행하지 말고 전달자에게 문의하세요.
- 앱 상태가 꼬였다고 느껴지면 Companion을 닫고 다시 `LUMOS.exe`를 실행하세요.
- 로컬 데이터를 초기화하려면 실행 폴더의 `data/` 폴더를 삭제하세요.

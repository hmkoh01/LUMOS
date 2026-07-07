# Closed Beta Intake & Download Readiness QA

## 목적

Closed beta 수동 모집과 download readiness 화면이 실제 backend나 installer 없이도 정직하게 동작하는지 확인한다.

## Route 확인

- `/beta` = 200
- `/download` = 200
- `/pricing` = 200
- `/` = 200
- `/app` 기존 제품 UI 유지

## Beta Page

- 수동 신청 안내가 보인다.
- `이메일 수집 backend는 없습니다` 문구가 있다.
- `신청 질문 복사하기` CTA가 있다.
- 질문 템플릿에 필수 질문 11개 이상이 있다.
- `mailto:` CTA가 있다.
- 일반 공개 다운로드가 아니라는 문구가 있다.
- 외부 form SaaS로 연결되지 않는다.

## Download Page

- `설치형 앱은 아직 준비 중입니다` 문구가 있다.
- `다운로드 버튼을 제공하지 않습니다` 문구가 있다.
- Windows portable build 예정임을 표시한다.
- 선정된 beta tester에게만 수동 배포 예정임을 표시한다.
- 개발 실행 명령은 외부 배포 방식이 아니라 preview로 분리되어 있다.

## Pricing / Landing CTA

- Landing primary CTA는 `/beta`로 이동한다.
- Pricing CTA는 실제 결제가 아니라 `/beta`로 이동한다.
- `/app`는 제품 미리보기 CTA로만 사용한다.
- 결제 provider 또는 checkout link가 없다.

## Copy-to-clipboard

- `landing.js`에 `data-copy-template` 처리 로직이 있다.
- clipboard API가 없을 때 fallback이 있다.
- 실패 시 한국어 toast가 표시된다.

## 금지 사항 확인

- 실제 회원가입 backend 없음
- 실제 이메일 수집 backend 없음
- 실제 결제 없음
- 실제 다운로드 파일 없음
- installer 생성 없음
- code signing / auto-update 없음

## 남은 수동 QA

- 실제 브라우저에서 복사 버튼 동작 확인
- mailto 앱이 열리는지 확인
- 1366x768 화면에서 beta 질문 템플릿이 읽기 좋은지 확인
- 모바일 폭에서 CTA가 겹치지 않는지 확인

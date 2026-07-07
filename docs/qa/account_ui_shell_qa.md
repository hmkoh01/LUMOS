# Account UI Shell QA

Date: 2026-07-05

## Scope

This QA covers the local account shell only. It does not validate real signup, login, OAuth, billing, token storage, or cloud backend behavior.

## Required Checks

### Local Mode

- Web UI sidebar shows `로컬 모드`.
- Settings tab includes a `계정` section.
- Account section says the app is currently used on this device.
- Account section says login is not connected.
- Device state says registration is not connected yet.
- Plan state says current state is local MVP.
- Existing Web UI flow is not blocked by login.

### Mock Auth Display

Open:

```text
/app?mockAuth=free#settings
/app?mockAuth=pro#settings
```

Check:

- `Mock Free 계정` appears for `mockAuth=free`.
- `Mock Pro 계정` appears for `mockAuth=pro`.
- Copy clearly says this is development/QA mock state.
- It does not look like real login.
- It does not enable real billing or plan management.

### Buttons

- `개발용 Cloud 연결 테스트` is clearly marked as a development connection
  check, not production login.
- `개발용 연결 해제` returns the section to local mode.
- `사용량 이벤트 테스트` only sends a non-sensitive dev test event.
- `계정 구조 보기` shows an informational toast only.
- `제품화 로드맵 보기` shows an informational toast only.

### Companion

- Companion status area shows `계정: 로컬 모드`.
- Companion does not add a login button.
- Companion does not add a billing or plan management button.
- `설정 화면 열기` still opens `/app#settings`.

### API Boundary

- No `/api/v1/auth/*` endpoints are added.
- No production token storage is implemented.
- No cloud backend call is made.

## Pass Criteria

- Local MVP remains usable without login.
- Account UI reads as a future-ready shell.
- Mock state is clearly marked as mock.
- Existing smoke test passes.

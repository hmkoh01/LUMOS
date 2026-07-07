# Auth API Contract

Date: 2026-07-05

## Implemented Development Skeleton

The Cloud Backend Minimal Auth Service phase implements a separate development
backend under `src/cloud/`.

Run:

```powershell
python run.py cloud
```

Default URL:

```text
http://127.0.0.1:8010
```

Default DB:

```text
data/cloud_lumos.db
```

Implemented now:

- `GET /health`
- `POST /auth/dev-login`
- `POST /auth/logout`
- `POST /auth/refresh`
- `GET /auth/me`
- `POST /devices/register`
- `GET /devices`
- `GET /entitlements/me`
- `POST /usage/events`

`POST /auth/dev-login` is a development-only email login for local contract
testing. It is not production signup/login, does not verify email ownership,
does not support OAuth, and must not be presented as commercial authentication.

## Local Dev Bridge

The local app exposes opt-in development bridge endpoints under
`/api/v1/product/cloud/*`.

- `GET /api/v1/product/cloud/status`
- `POST /api/v1/product/cloud/dev-connect`
- `POST /api/v1/product/cloud/dev-disconnect`
- `GET /api/v1/product/cloud/account`
- `POST /api/v1/product/cloud/usage-test`

These endpoints are not production auth APIs. They exist so the Web UI settings
account shell can verify `dev-login -> me -> device register -> entitlement ->
usage event` without making the local MVP depend on the cloud backend.

Dev tokens are kept in process memory only and must not be written to SQLite,
files, or keychain in this phase.

Updated token storage policy:

- default dev bridge token storage remains memory-only
- optional keyring prototype may be enabled with `LUMOS_DEV_PERSIST_TOKENS=1`
- token values are never returned to the Web UI
- token values must not be stored in SQLite or browser storage

## A. Purpose

Entitlement responses in the development cloud backend now include
cache-friendly metadata:

- `fetched_at`
- `expires_at`
- `grace_until`
- `source`
- `is_dev`

These fields are policy hints for local cache/grace handling, not
billing-backed subscription proof.

This contract defines how the future LUMOS local app will talk to a Cloud Backend for authentication, device registration, entitlement checks, and usage metering.

This remains a production contract draft. A development-only subset now exists
in `src/cloud/`, while the local MVP must continue working without login.

## B. Endpoint Draft

### POST /auth/signup

Purpose:

- create a user account

Auth required:

- no

Request:

```json
{
  "email": "user@example.com",
  "password": "handled-by-future-backend",
  "name": "User"
}
```

Response:

```json
{
  "user": {
    "id": "user_123",
    "email": "user@example.com",
    "name": "User",
    "status": "active"
  },
  "session": {
    "access_token": "short_lived_token",
    "refresh_token": "refresh_token",
    "expires_at": "2026-07-05T12:00:00Z"
  }
}
```

Error cases:

- EMAIL_ALREADY_EXISTS
- INVALID_EMAIL
- WEAK_PASSWORD
- SERVER_ERROR

Local app use:

- optional first product account flow before or after local onboarding

Security notes:

- password handling belongs to the cloud backend only
- local app should never store a password

### POST /auth/login

Purpose:

- create a session for an existing user

Auth required:

- no

Request:

```json
{
  "email": "user@example.com",
  "password": "handled-by-future-backend",
  "device_hint": {
    "device_name": "Koh's PC",
    "os": "Windows",
    "app_version": "0.1.0"
  }
}
```

Response:

```json
{
  "user": {
    "id": "user_123",
    "email": "user@example.com",
    "name": "User",
    "plan": "pro"
  },
  "session": {
    "access_token": "short_lived_token",
    "refresh_token": "refresh_token",
    "expires_at": "2026-07-05T12:00:00Z"
  }
}
```

Error cases:

- INVALID_CREDENTIALS
- ACCOUNT_DISABLED
- TOO_MANY_ATTEMPTS
- SERVER_ERROR

Local app use:

- login screen or account tab

Security notes:

- access token should be short-lived
- refresh token must be protected by OS keychain when implemented

### POST /auth/logout

Purpose:

- revoke current session

Auth required:

- yes

Request:

```json
{
  "refresh_token": "refresh_token"
}
```

Response:

```json
{
  "success": true
}
```

Error cases:

- AUTH_REQUIRED
- TOKEN_EXPIRED
- SERVER_ERROR

Local app use:

- account logout

Security notes:

- local token cache must be cleared even if network revoke fails

### POST /auth/refresh

Purpose:

- exchange refresh token for a new access token

Auth required:

- refresh token

Request:

```json
{
  "refresh_token": "refresh_token",
  "device_id": "device_123"
}
```

Response:

```json
{
  "access_token": "new_short_lived_token",
  "refresh_token": "optional_rotated_refresh_token",
  "expires_at": "2026-07-05T12:00:00Z"
}
```

Error cases:

- TOKEN_EXPIRED
- TOKEN_REVOKED
- DEVICE_REVOKED
- SERVER_ERROR

Local app use:

- app startup
- background entitlement refresh

Security notes:

- refresh token rotation is preferred

### GET /auth/me

Purpose:

- return current user profile

Auth required:

- yes

Response:

```json
{
  "user": {
    "id": "user_123",
    "email": "user@example.com",
    "name": "User",
    "plan": "pro",
    "status": "active"
  }
}
```

Error cases:

- AUTH_REQUIRED
- TOKEN_EXPIRED
- ACCOUNT_DISABLED

Local app use:

- account tab
- startup session validation

### POST /devices/register

Purpose:

- register the current local app installation

Auth required:

- yes

Request:

```json
{
  "device_name": "Koh's PC",
  "os": "Windows",
  "app_version": "0.1.0",
  "device_fingerprint_hash": "hashed-placeholder"
}
```

Response:

```json
{
  "device": {
    "id": "device_123",
    "user_id": "user_123",
    "device_name": "Koh's PC",
    "os": "Windows",
    "app_version": "0.1.0",
    "status": "active"
  }
}
```

Error cases:

- AUTH_REQUIRED
- DEVICE_LIMIT_EXCEEDED
- DEVICE_BLOCKED

Local app use:

- after login
- before entitlement checks

Security notes:

- fingerprinting must be minimal and privacy-aware
- do not collect invasive hardware identifiers without review

### GET /devices

Purpose:

- list registered devices

Auth required:

- yes

Response:

```json
{
  "devices": []
}
```

Local app use:

- future account management page

### PATCH /devices/{device_id}

Purpose:

- update device metadata

Auth required:

- yes

Request:

```json
{
  "device_name": "Work Laptop",
  "app_version": "0.2.0"
}
```

Error cases:

- AUTH_REQUIRED
- DEVICE_NOT_FOUND
- DEVICE_REVOKED

### DELETE /devices/{device_id}

Purpose:

- revoke a device

Auth required:

- yes

Response:

```json
{
  "success": true
}
```

Local app use:

- future account management

### GET /entitlements/me

Purpose:

- return plan-derived rights for the current user/device

Auth required:

- yes

Response:

```json
{
  "plan": "pro",
  "entitlements": {
    "max_signals_per_day": "10",
    "auto_briefing_enabled": "true",
    "context_connectors_enabled": "true"
  },
  "offline_grace_until": "2026-07-12T00:00:00Z"
}
```

Error cases:

- AUTH_REQUIRED
- SUBSCRIPTION_INACTIVE
- ENTITLEMENT_DENIED
- SERVER_ERROR

Local app use:

- app startup
- before gated feature usage

### POST /usage/events

Purpose:

- record usage metering events

Auth required:

- yes

Request:

```json
{
  "device_id": "device_123",
  "event_type": "signal_generated",
  "quantity": 1,
  "metadata_json": {
    "mode": "mock"
  }
}
```

Response:

```json
{
  "success": true
}
```

Security notes:

- metadata must not include raw browser history, local paths, file contents, private URLs, or tokens

## C. Token Policy

- Access token: short-lived, used for API calls.
- Refresh token: longer-lived, stored in OS keychain when implemented.
- Expiration: local app refreshes access token before expiry.
- Logout: revoke refresh token and clear local token cache.
- Device binding: refresh tokens should be associated with a registered device.
- Offline grace: app may continue using cached entitlements for a limited period.

This phase only uses mock tokens marked as mock.

## D. Error Code Draft

- AUTH_REQUIRED
- TOKEN_EXPIRED
- TOKEN_REVOKED
- DEVICE_LIMIT_EXCEEDED
- DEVICE_REVOKED
- SUBSCRIPTION_INACTIVE
- ENTITLEMENT_DENIED
- NETWORK_UNAVAILABLE
- SERVER_ERROR

## E. Local App Korean UX Copy

| Error | User-facing copy |
| --- | --- |
| AUTH_REQUIRED | 로그인이 필요해요. 계속하려면 계정에 로그인해주세요. |
| TOKEN_EXPIRED | 로그인 시간이 만료됐어요. 다시 로그인해주세요. |
| DEVICE_LIMIT_EXCEEDED | 등록 가능한 기기 수를 초과했어요. 사용하지 않는 기기를 해제해주세요. |
| SUBSCRIPTION_INACTIVE | 구독 상태를 확인할 수 없어요. 요금제 상태를 확인해주세요. |
| ENTITLEMENT_DENIED | 현재 요금제에서는 사용할 수 없는 기능이에요. |
| NETWORK_UNAVAILABLE | 인터넷 연결이 불안정해요. 잠시 후 다시 시도해주세요. |
| SERVER_ERROR | LUMOS 서버에 일시적인 문제가 있어요. 다시 시도해주세요. |

## Non-Goals

- no real backend implementation
- no OAuth provider
- no password handling in local app
- no production token storage

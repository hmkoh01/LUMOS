# Cloud Auth Service QA

This QA note covers the development-only cloud backend skeleton added for the
Cloud Backend Minimal Auth Service phase.

## Scope

- The cloud backend is separate from the local MVP app.
- It uses `data/cloud_lumos.db`.
- It does not make the Web UI login-required.
- It does not implement OAuth, password login, billing, email verification, or
  production token storage.

## Run

```powershell
python run.py cloud
```

Expected:

- Server starts on `http://127.0.0.1:8010`.
- `GET /health` returns `status: ok`.
- The response includes `dev_only: true`.

## Endpoint Checklist

1. `POST /auth/dev-login`
   - Send `email`, `name`, and optional `plan`.
   - Expect `dev_access_...` and `dev_refresh_...` tokens.
   - Confirm the user is created or updated.

2. `GET /auth/me`
   - Use `Authorization: Bearer <access_token>`.
   - Expect current user and session data.
   - Invalid or revoked tokens should return `401`.

3. `POST /auth/refresh`
   - Send the refresh token from dev login.
   - Expect a new `dev_access_...` token.

4. `POST /devices/register`
   - Use bearer auth.
   - Send `device_name`, `os`, `app_version`, and a placeholder fingerprint hash.
   - Re-registering the same user and fingerprint should reuse the device row.

5. `GET /devices`
   - Use bearer auth.
   - Expect registered devices for the current user.

6. `GET /entitlements/me`
   - Use bearer auth.
   - Expect Free/Pro/Team style entitlement keys.
   - This is dev plan data, not billing-backed subscription state.

7. `POST /usage/events`
   - Use bearer auth.
   - Store only minimal metadata.
   - Do not send browser history, local file text, private URLs, tokens, or raw
     personal context.

8. `POST /auth/logout`
   - Use bearer auth.
   - Expect the current session to be revoked.
   - A later `GET /auth/me` with the same token should return `401`.

## DB Separation

- Local MVP DB: `data/lumos.db`
- Demo DB: `data/demo_lumos.db`
- Cloud auth skeleton DB: `data/cloud_lumos.db`

`cloud_lumos.db` must not be used by the local signal pipeline or demo reset
commands.

## Production Gaps

- No OAuth provider.
- No password auth.
- No email verification or password reset.
- No billing webhook.
- No production token rotation policy.
- No admin UI or audit log.
- No secure local token storage integration.

## Related Local Bridge QA

After the cloud backend passes this endpoint checklist, verify the opt-in local
bridge from the Web UI settings account shell:

- `docs/qa/local_cloud_dev_connection_qa.md`

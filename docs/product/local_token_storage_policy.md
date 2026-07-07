# Local Token Storage Policy

Date: 2026-07-05

## Purpose

Define how the future local app should store account/session/device state. This phase does not implement production token storage.

## Implemented Prototype Boundary

This phase adds `src/product/token_store.py`.

Implemented:

- `TokenBundle`
- `InMemoryTokenStore`
- `KeyringTokenStore`
- optional keyring-backed prototype
- token redaction in `repr` / `str`

Not implemented:

- production login
- OAuth
- billing
- automatic token refresh loop
- background session manager
- Web UI token storage

The default local-cloud dev bridge remains memory-only. Persistent dev token
storage is attempted only when `LUMOS_DEV_PERSIST_TOKENS=1` is explicitly set.

## Stored Auth Data

Allowed auth storage fields:

- access token
- refresh token
- token type
- session expiry
- user id
- device id
- dev/prototype flag
- stored timestamp
- entitlement cache timestamp
- last successful auth check

## Data That Must Not Be Stored With Tokens

- raw browser history
- local file content
- private context snippets
- full source item raw payloads
- full signal raw payloads
- token values in Web UI `localStorage` or `sessionStorage`

## Storage Principles

- Do not store production refresh tokens in plaintext.
- Prefer OS keychain or credential manager.
- Keep auth token storage separate from the local SQLite product database.
- Clear tokens on logout.
- Keep local device id separate from raw personal context data.
- Store only the minimum auth metadata needed for app startup.

## Recommended Future Storage

Windows:

- Windows Credential Manager or DPAPI-backed storage

macOS:

- Keychain

Linux:

- Secret Service/libsecret where available

MVP fallback:

- mock tokens only
- explicit `is_mock = true`
- no production secrets
- memory-only for the default dev bridge
- keyring prototype only when explicitly enabled

Development fallback:

- no plaintext token file by default
- no token storage in SQLite
- no token values in browser storage
- if keyring is unavailable, fall back to memory-only or fail safely

## Token Types

Access token:

- short-lived
- can be kept in memory
- may be cached only if protected

Refresh token:

- long-lived
- must use secure storage
- should rotate where possible

Device id:

- can be stored locally as non-secret account metadata
- should not include raw hardware identifiers

## Offline Grace

The app may cache:

- user id
- device id
- plan name
- entitlement summary
- last checked time
- grace period expiry

If offline and within grace:

- continue allowed local features
- show a soft status message if needed
- use cached entitlement summary only for a limited period
- make it clear that cloud validation is temporarily unavailable

If offline and grace expired:

- keep local data accessible
- ask the user to reconnect for subscription validation
- fall back to Free/local mode behavior where appropriate

## Logout

On logout:

- delete refresh token
- delete access token
- clear cached auth state
- expire entitlement cache
- decide separately whether to keep a non-secret device id

## Threat Model Draft

Risks to address before production:

- local malware reading process memory
- plaintext token leakage
- browser storage leakage
- local DB backup leakage
- shared PC account confusion
- stolen refresh token reuse
- logout not clearing tokens
- cloud token accidentally logged in errors

Prototype mitigations in this phase:

- `TokenBundle.__repr__` and `__str__` redact token values
- default dev bridge keeps token state in memory only
- optional keyring use is explicit
- token values are not returned to the Web UI
- token values are not saved in SQLite

- revoke session if network is available
- delete local access token
- delete local refresh token
- keep local data unless the user chooses to delete it
- keep device id only if future UX needs "remember this device"; otherwise clear it

## Risks

- plaintext token leakage
- copying token cache in backups
- confusing local data deletion with account logout
- collecting too much device fingerprint data
- losing access when offline if grace rules are too strict

## Current Phase Decision

Only mock tokens are implemented. Production token storage is intentionally deferred until OS-specific secure storage is selected.

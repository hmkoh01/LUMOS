# Local Secure Token Storage QA

This QA note covers the Local Secure Token Storage Design & Prototype phase.

## Purpose

Verify that LUMOS has a token storage abstraction that can evolve toward
production secure storage without changing the default local MVP behavior.

## Scope

- No production login.
- No OAuth.
- No billing.
- No Web UI token storage.
- No SQLite plaintext refresh token storage.
- Default dev bridge remains memory-only.

## Memory-Only Test

Expected:

- `InMemoryTokenStore.save_tokens()` stores a `TokenBundle`.
- `load_tokens()` returns the bundle.
- `clear_tokens()` removes the bundle.
- `has_tokens()` returns false after clear.

## Token Redaction Test

Expected:

- `repr(TokenBundle)` does not include access token value.
- `str(TokenBundle)` does not include refresh token value.
- Test output should only show `<redacted>` for token fields.

## Keyring Available Test

If Python `keyring` and a working OS backend are available:

1. Create `KeyringTokenStore`.
2. Save a dev `TokenBundle`.
3. Load it.
4. Confirm metadata round-trips.
5. Clear it.

This is still a prototype, not production security certification.

## Keyring Unavailable Test

If keyring is missing or no OS backend is available:

- app import must not fail
- `KeyringTokenStore` should raise `TokenStoreUnavailable`
- default bridge should remain memory-only
- Web UI should remain usable

## Dev Bridge Relationship

Default:

- `token_storage: memory`
- dev token stored in process memory only
- app restart clears state

Optional prototype:

```powershell
$env:LUMOS_DEV_PERSIST_TOKENS = "1"
```

Expected:

- bridge attempts keyring storage
- if unavailable, summary becomes `keyring_unavailable_memory`
- no token values are returned to Web UI

## Disconnect / Logout

Click `개발용 연결 해제`.

Expected:

- cloud logout is attempted
- bridge clears token store
- account shell returns to local mode

## Remaining Production Risks

- no token rotation policy
- no refresh retry strategy
- no encrypted entitlement cache
- no OS-specific install hardening
- no shared-device account UX
- no admin/audit visibility

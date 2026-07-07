# Entitlement Cache & Offline Grace QA

## Purpose

Verify that local LUMOS can cache cloud entitlement summaries and fall back
smoothly when cloud is unavailable.

## Scope

- No billing provider.
- No real subscription validation.
- No feature gate enforcement.
- No token in entitlement cache.
- Local MVP remains usable without cloud.

## Unit-Level Checks

1. Create `EntitlementSnapshot`.
2. Save it to `InMemoryEntitlementCache`.
3. Load it.
4. Confirm `status = valid` before `expires_at`.
5. Confirm `status = grace` after `expires_at` and before `grace_until`.
6. Confirm fallback after `grace_until`.
7. Clear the cache.

## Bridge Checks

Run cloud:

```powershell
python run.py cloud
```

Run local app:

```powershell
python run.py app
```

Then:

1. Open `/app#settings`.
2. Click `개발용 Cloud 연결 테스트`.
3. Confirm account shell shows entitlement summary.
4. Confirm cache status is valid.
5. Stop cloud backend.
6. Confirm local mode remains usable.
7. Confirm account/status endpoint can still return cached or grace state.
8. Click `개발용 연결 해제`.
9. Confirm dev cache is cleared.

## Expected Fields

Bridge responses should include:

- `entitlement_cache.status`
- `entitlement_cache.decision`
- `entitlement_cache.expires_at`
- `entitlement_cache.grace_until`
- `entitlement_summary`

They must not include:

- access token
- refresh token
- browser history
- local file content
- private context snippets

## Remaining Risks

- cache is currently in-memory only
- no encrypted persistent entitlement cache
- no production billing source-of-truth
- no real feature gate enforcement yet
- no Team policy

## Related QA

- `docs/qa/entitlement_gate_integration_qa.md`

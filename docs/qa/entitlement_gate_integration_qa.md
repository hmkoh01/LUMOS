# Entitlement Gate Integration QA

## Purpose

Verify that Free / Pro / Team feature gate decisions are visible and testable
without blocking the local MVP.

## Endpoint Checks

1. `GET /api/v1/product/gates/status`
   - returns `is_enforced: false`
   - returns gate summary list
   - local mode remains allowed

2. `POST /api/v1/product/gates/evaluate`
   - accepts `feature_key`
   - accepts optional `current_value`
   - returns `allowed: true`
   - returns `is_enforced: false`

## Plan Checks

- Free: signal count above 3 returns upgrade guidance.
- Pro: signal count up to Pro limit is allowed.
- Unknown plan: Free-safe/local guidance, not a hard block.
- Grace cache: message says cloud check is needed.
- Expired cache: message falls back to local mode.

## Web UI Checks

- Settings account section shows `요금제별 기능 안내`.
- Signal count over Free default shows soft warning.
- Saving settings is not blocked.
- Source toggles are not blocked.
- No real payment or upgrade link is active.

## Non-Goals

- no billing provider
- no production hard gate
- no login-required Web UI
- no token use in gate service


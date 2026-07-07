# Implementation Roadmap

Date: 2026-06-30

## Current Phase Update

`Cloud Backend Minimal Auth Service` adds a separate development-only FastAPI
backend under `src/cloud/`.

Completed boundary:

- `python run.py cloud`
- `data/cloud_lumos.db`
- `/auth/dev-login`
- `/auth/me`
- `/auth/refresh`
- `/auth/logout`
- `/devices/register`
- `/devices`
- `/entitlements/me`
- `/usage/events`

Still intentionally not implemented:

- production signup/login
- OAuth
- password auth
- billing
- installer/update/signing
- login-required Web UI

The next production step is to decide how the Local Account UI Shell should
connect to this cloud boundary without breaking local mode.

## Local Cloud Dev Connection Update

The Settings account shell now connects to the development cloud backend through
local bridge endpoints only when the user explicitly clicks the development
connection test button.

Implemented:

- `/api/v1/product/cloud/status`
- `/api/v1/product/cloud/dev-connect`
- `/api/v1/product/cloud/dev-disconnect`
- `/api/v1/product/cloud/account`
- `/api/v1/product/cloud/usage-test`

Still forbidden/not implemented:

- login-required Web UI
- production token storage
- password login
- OAuth
- billing

Next likely phase: secure local token storage design and a production auth UI
shell that can coexist with local mode.

## Local Secure Token Storage Update

Implemented prototype:

- `src/product/token_store.py`
- `TokenBundle`
- `InMemoryTokenStore`
- optional `KeyringTokenStore`
- token redaction in string representations
- dev bridge token storage summary

Default behavior remains memory-only. Optional persistent dev token storage is
enabled only with `LUMOS_DEV_PERSIST_TOKENS=1`.

Next likely phase: entitlement cache and offline grace policy integration.

## Phase 1. Production Readiness Architecture

## Entitlement Cache & Offline Grace Update

Implemented prototype:

- `src/product/entitlement_cache.py`
- in-memory entitlement snapshot cache
- TTL/grace evaluation
- local bridge response cache status
- Web UI account shell entitlement cache/grace summary

Still not implemented:

- billing provider validation
- real subscription source of truth
- feature gate enforcement
- persistent encrypted entitlement cache

Next likely phase: Entitlement Gate Integration for non-critical limits, still
without billing enforcement.

## Entitlement Gate Integration Update

Implemented:

- `src/product/feature_gates.py`
- soft gate decisions
- `/api/v1/product/gates/status`
- `/api/v1/product/gates/evaluate`
- Web UI feature guidance panel

Still not implemented:

- production hard gate
- billing-backed entitlement enforcement
- active upgrade/payment flow

Next likely phase: Landing & pricing validation or billing provider selection
document, before any real payment integration.

Purpose:

- define local/cloud/landing architecture
- define account/device/subscription/entitlement model
- define privacy and packaging principles

Scope:

- docs
- interface scaffold
- no runtime behavior change

Forbidden:

- real login
- billing
- installer
- cloud API calls

Completion:

- product docs exist
- scaffold imports pass
- existing MVP and demo mode still pass smoke tests

Risk:

- over-designing before user validation

## Phase 2. Account & Device Auth Foundation

Purpose:

- define auth API contracts and local auth boundaries
- prepare mock auth/device/entitlement services
- keep the local MVP usable without login

Scope:

- auth API contract
- local token storage policy
- auth state model
- mock login/logout/refresh
- mock device registration
- mock entitlement lookup
- auth UI wireframe

Forbidden:

- real signup
- real login backend
- OAuth provider integration
- billing
- production token storage
- forcing current Web UI to require login

Expected files:

- `docs/product/auth_api_contract.md`
- `docs/product/local_token_storage_policy.md`
- `docs/product/auth_ui_wireframe.md`
- `src/product/auth_state.py`
- `src/product/auth_service.py`
- `src/product/cloud_client.py`
- `src/product/device.py`
- `src/product/entitlements.py`

Completion:

- mock login/logout/refresh passes tests
- mock device registration passes tests
- Free/Pro entitlement mock passes tests
- current MVP and demo mode remain unchanged

Risk:

- confusing mock auth with production security
- over-designing before choosing cloud backend

## Next Phase Candidates After Phase 2

### Local Account UI Shell

Purpose:

- create non-blocking account surfaces in Web UI/Companion
- show local mode clearly
- support development-only mock auth display

Forbidden:

- requiring login for local MVP
- real OAuth or password handling

Completion:

- settings tab has an account section
- sidebar/Companion show local mode
- `?mockAuth=free/pro` is visibly mock-only
- no auth endpoint is added

### Cloud Backend Minimal Auth Service

Purpose:

- choose backend stack and implement real auth endpoints

Forbidden:

- billing
- broad telemetry
- uploading raw personal context
- forcing all local MVP use through login

### Entitlement Gate Integration

Purpose:

- apply Free/Pro limits using entitlement service

Forbidden:

- hard lockouts that hide local data
- real payment provider before billing phase

### Landing & Download Page

Purpose:

- explain product, collect waitlist, and offer download instructions

Forbidden:

- checkout before billing exists

### Closed Beta Invite System

Purpose:

- control user rollout and learn from real usage

Forbidden:

- public launch
- team workspace features

## Phase 3. Entitlement / Plan Gate

Purpose:

- apply Free/Pro rights without billing integration first

Scope:

- entitlement API
- local cache
- Free limit UI
- mock/admin-assigned Pro

Forbidden:

- real payment provider
- hard lockouts that damage local data

Completion:

- plan limits are visible and enforceable
- offline grace works

Risk:

- making Free UX feel punitive

## Phase 4. Landing & Download Page

Purpose:

- explain product and collect early users

Scope:

- landing page
- pricing copy
- download instructions
- privacy/security pages
- waitlist or invite request

Forbidden:

- checkout before billing is ready
- unsupported legal/security claims

Completion:

- users can understand product and download/test

Risk:

- overpromising beyond MVP

## Phase 5. Windows Packaging

Purpose:

- reduce command-line friction

Scope:

- portable Windows build
- version info
- release notes
- basic logs

Forbidden:

- auto-update
- code signing claims before signing exists

Completion:

- invited user can run LUMOS without Python setup

Risk:

- packaging instability
- antivirus false positives

## Phase 6. Closed Beta Invite System

Purpose:

- control rollout and learn from real users

Scope:

- invite codes or allowlist
- beta onboarding
- support feedback channel
- minimal admin visibility

Forbidden:

- broad public launch
- team features

Completion:

- 10-30 invited users can onboard and report issues

Risk:

- support overhead

## Phase 7. Billing Integration

Purpose:

- convert validated usage into paid subscription

Scope:

- billing provider
- checkout
- billing webhooks
- subscription status
- cancellation/refund handling

Forbidden:

- custom payment storage
- storing card details directly

Completion:

- payment updates entitlement state

Risk:

- legal/refund obligations
- webhook consistency

## Phase 8. Operations / Admin / Telemetry

Purpose:

- operate product responsibly

Scope:

- usage metering
- crash/error telemetry
- cost monitoring
- admin dashboard
- release health

Forbidden:

- collecting raw personal context as telemetry

Completion:

- operator can see failures, cost, usage, and version health

Risk:

- privacy overreach

## Roadmap Rule

Advance only when the previous phase has a user-visible validation reason. Do not add billing, packaging, or team features before the core daily signal value is validated.

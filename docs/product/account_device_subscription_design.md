# Account, Device, Subscription, Entitlement Design

Date: 2026-06-30

## Current Implementation Boundary

The current codebase has a minimal development cloud backend skeleton in
`src/cloud/`.

- Cloud DB: `data/cloud_lumos.db`
- Local MVP DB: `data/lumos.db`
- Demo DB: `data/demo_lumos.db`

Implemented for contract validation:

- development-only email login through `/auth/dev-login`
- user rows
- device rows
- session rows with hashed dev token storage
- plan entitlement snapshot rows
- usage event rows

Not implemented yet:

- production signup/login
- password auth
- OAuth
- email verification
- billing-backed subscriptions
- secure local token storage
- account UI connected to the cloud backend

The Web UI and Companion remain usable in local mode without login.

## Entitlement Cache Boundary

`entitlements.py` defines plan-level permission templates.
`entitlement_cache.py` stores and evaluates the current user's latest cloud
entitlement snapshot.

Current prototype:

- in-memory cache only
- 24 hour TTL
- 7 day offline grace
- no token storage
- no feature gate enforcement

Future feature gates should read entitlement cache status but must still keep
local data accessible when cloud is unavailable.

## Feature Gate Boundary

`feature_gates.py` maps entitlement summaries to feature-level decisions.

Current rules:

- gate decisions are soft
- `is_enforced` remains false
- local MVP flows are not blocked
- unknown plan falls back to local/Free-safe guidance
- grace status adds a cloud-check-needed message

## A. Core Concepts

- **User**: the account owner.
- **Device**: a registered local app installation.
- **Session**: authenticated access from a device.
- **Plan**: a commercial package such as Free, Pro, or Team.
- **Subscription**: a user's active billing relationship to a plan.
- **Entitlement**: a concrete permission or limit derived from the plan.
- **Usage Meter**: event log used to enforce limits and understand cost.
- **License Check**: app startup or periodic validation that the current device can use the plan.

## B. Data Model Draft

### users

- id
- email
- password_hash or oauth_provider
- name
- created_at
- last_login_at
- status

### devices

- id
- user_id
- device_name
- os
- app_version
- device_fingerprint_hash
- registered_at
- last_seen_at
- status

### sessions

- id
- user_id
- device_id
- access_token_hash
- refresh_token_hash
- expires_at
- created_at
- revoked_at

### plans

- id
- name
- price_monthly
- billing_interval
- description
- status

### subscriptions

- id
- user_id
- plan_id
- status
- provider
- provider_customer_id
- provider_subscription_id
- current_period_start
- current_period_end
- cancel_at_period_end

### entitlements

- plan_id
- key
- value
- description

### usage_events

- id
- user_id
- device_id
- event_type
- quantity
- metadata_json
- created_at

## C. Free / Pro / Team Draft

### Free

- limited daily signals
- basic sources
- limited manual generation
- limited history
- limited personal context connectors
- local-first onboarding

### Pro

- more daily signals
- automatic briefing
- advanced sources
- longer history
- expanded personal context connectors
- higher usage limits
- priority processing if cloud processing is added later

### Team

- team workspace
- shared briefing
- member management
- admin settings
- team billing
- shared source presets

Team should not be implemented until individual Pro value is validated.

## D. Applying Entitlements In The Local App

Recommended flow:

1. App starts.
2. App loads cached session.
3. App checks cloud entitlement if online.
4. App caches entitlement result locally.
5. App applies limits to generation, source access, history, and connector availability.
6. If offline, app uses a grace period.
7. If entitlement expires, app shows a user-friendly explanation and keeps local data accessible.

UX rules:

- Do not punish the user for temporary network failure.
- Free limits should explain value, not block aggressively.
- A plan downgrade should not delete local data.
- Upgrade prompts should appear at meaningful moments, such as hitting a daily signal limit.

## E. Immediate Preparation For Current Code

Allowed now:

- define account/device/entitlement namespace
- define dataclasses and service interfaces
- define local token storage location in documentation
- define cloud client interface
- define entitlement service interface

Not allowed yet:

- actual login UI
- real token storage implementation
- network calls to a cloud API
- billing provider integration
- plan gates inside current Web UI

The scaffold under `src/product/` exists only to make later implementation boundaries clear.

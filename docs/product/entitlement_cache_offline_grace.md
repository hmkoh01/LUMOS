# Entitlement Cache & Offline Grace

Date: 2026-07-05

## Purpose

Entitlement cache lets the local app keep a recent account/plan summary when the
cloud backend is temporarily unavailable.

Goals:

- avoid losing account state immediately when cloud is offline
- reduce app startup UX delay
- keep the local-first MVP usable
- prepare policy boundaries for future paid feature gates

This is not billing-backed subscription validation.

## Cache Data

Allowed:

- user id
- device id
- plan
- entitlement key/value summary
- fetched_at
- expires_at
- grace_until
- source: `cloud_dev` or future production source
- is_dev
- last_successful_check_at

Forbidden:

- access token
- refresh token
- browser history
- local file content
- raw context snippets
- full source item payloads
- full signal raw payloads
- sensitive URL/token/path values
- billing provider raw payload

## Prototype Policy

Current defaults:

- cache TTL: 24 hours
- offline grace: 7 days
- cache backend: in-memory prototype
- source: `cloud_dev`

During valid cache:

- show the most recent entitlement summary
- do not enforce paid limits yet

During offline grace:

- show cached entitlement as temporarily usable
- tell the user cloud validation is unavailable
- keep local MVP usable

After grace expires:

- fall back to local mode or Free-safe mode
- preserve access to local data
- future Pro-only actions can be gated later

## UX Copy

- Normal: `권한 확인: 방금 Cloud에서 확인됨`
- Cloud unavailable with cache: `권한 확인: Cloud 연결 실패 · cached 권한 사용 중`
- Grace: `권한 확인: Offline grace 적용 중`
- Expired: `권한 확인: 만료됨 · 로컬 모드로 사용 중`
- Local fallback: `Cloud가 꺼져 있어도 로컬 모드는 계속 사용할 수 있어요.`

## Production Review

Before billing integration:

- define subscription cancellation grace
- define refund/chargeback behavior
- decide device limit behavior during offline grace
- define Team workspace grace policy
- add abuse controls
- add billing webhook source-of-truth rules

## Feature Gate Relationship

Feature gates may read entitlement cache status, but this prototype does not
enforce paid limits. During `valid` and `grace` states, the UI may show cached
plan guidance. During `expired` or `empty` states, gates should return local
mode / Free-safe soft guidance.

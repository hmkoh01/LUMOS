# Entitlement Gate Policy

Date: 2026-07-05

## Purpose

Map Free / Pro / Team entitlements to LUMOS product features.

This phase is a soft gate prototype. It does not implement billing-backed
subscription validation and does not block the current local MVP workflow.

## Feature Gate Candidates

- today signal count
- daily generate limit
- source count
- automatic briefing
- advanced sources
- personal context connectors
- history retention
- team workspace
- export/share
- priority processing
- cloud sync

## Plan Draft

### Free

- today signals: 3
- basic sources
- manual generation limit later
- limited history
- personal context connector limit later
- local mode remains usable

### Pro

- more today signals
- automatic briefing
- advanced sources
- expanded personal context connectors
- longer history
- priority processing candidate

### Team

- team workspace
- shared briefing
- member management
- team billing
- admin settings

## Soft Gates In This Phase

- signal count guidance
- source count guidance
- auto briefing guidance
- advanced source guidance
- context connector guidance
- history days guidance
- team workspace guidance

## Never Block In This Phase

- viewing today's signals
- onboarding
- feedback
- local mode usage
- demo mode usage
- settings page access
- source page access

## Hard Gate Prerequisites

- production login
- billing-backed subscription
- secure token storage
- persistent entitlement cache
- refund/cancel/chargeback policy
- offline grace policy
- customer support flow


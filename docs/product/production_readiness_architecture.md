# Production Readiness Architecture

Date: 2026-06-30

## A. Current State

LUMOS currently works as a local MVP:

- Local Web UI served at `/app`
- Desktop Companion launcher/controller
- Local SQLite database
- First-run onboarding
- Korean Briefing Layer
- RSS, Hacker News, GitHub, and mock collectors
- Signal generation pipeline
- Personal context sync
- Interest control
- Feedback loop
- Demo DB and demo mode
- QA/demo documents for mentoring and user testing

Commercial product capabilities not implemented yet:

- signup/login
- user accounts
- cloud backend
- device registration
- subscription status
- plan-based entitlements
- billing
- packaged download/installer
- landing website
- legal/privacy policy
- operations monitoring
- crash/error telemetry

## B. Target Product Structure

LUMOS should become a local + cloud hybrid subscription product.

### 1. Local Desktop App

Role:

- collect and process personal context locally
- read browser history and local files only when the user opts in
- keep raw local context on the device by default
- maintain part of the interest graph locally
- show today's signals through the local Web UI shell
- run Companion and future notification surfaces
- store login/session tokens safely
- check subscription status and entitlement cache
- apply usage limits locally
- keep demo mode for sales/mentoring/testing only

The local app remains the primary place where sensitive personal context is handled.

### 2. Cloud Backend

Role:

- signup/login
- user account management
- device registration
- subscription status
- entitlement validation
- billing webhook receiver
- license/session validation
- remote config
- usage metering
- release/version check
- crash/error telemetry
- minimal server-side user profile

The cloud backend should not become the default storage location for raw browser history, local file contents, private URLs, or personal document text.

### 3. Landing Website

Role:

- product positioning
- pricing
- download
- signup/login
- account management
- billing management
- privacy policy
- terms of service
- FAQ
- contact/support

The landing website sells and explains the product. The Web UI at `/app` remains the local product interface.

## C. Local-First Principles

LUMOS handles personal context, so the default architecture must be local-first.

Principles:

- Browser history and local file raw contents stay local by default.
- Cloud receives account, subscription, usage, and minimum settings data.
- Personal context is used only when the user explicitly enables a connector.
- Full raw source data is not uploaded to the server by default.
- The user must be able to turn off connectors.
- The user must be able to delete local context data.
- Future cloud sync must be opt-in.
- Any summary-level profile sync must be clearly explained.
- Sensitive URLs, local paths, tokens, and document contents must not be sent as telemetry.

## D. Product Sales Flow

Target commercial flow:

1. User visits landing page.
2. User reads product positioning and pricing.
3. User signs up or starts Free.
4. User downloads the app.
5. User installs or runs the app.
6. User logs in.
7. App registers the device.
8. App checks subscription and entitlements.
9. User completes onboarding.
10. User receives the first Korean briefing.
11. User gives feedback: save, not interested, keep tracking.
12. Product prompts Pro upgrade when a useful limit is reached.
13. User manages billing on the website.

## E. Gap Between MVP And Product

| Area | Current MVP | Production Need |
| --- | --- | --- |
| Authentication | None | Email/OAuth login, sessions, token refresh |
| User data | Local SQLite only | Local DB plus cloud account identity |
| Device identity | None | Device registration and license validation |
| Subscription | None | Plan, subscription status, billing webhooks |
| Entitlements | None | Feature limits and cached plan rights |
| Distribution | Python command | Portable app, installer, signed release later |
| Landing | None | Product page, pricing, download, FAQ |
| Legal | Sparse docs | Privacy policy, terms, copyright/source policy |
| Operations | Local logs/tests | Usage metrics, crash/error telemetry, admin view |
| Cost control | Not needed locally | API usage metering, rate limits, plan-linked costs |
| Support | README/docs | Support channel, troubleshooting, account help |

## Non-Goals For This Phase

- no actual login
- no signup
- no payment provider
- no installer
- no auto-update
- no cloud API implementation
- no change to local signal pipeline
- no change to demo mode

# Cloud / Local Split

Date: 2026-06-30

## A. Data That Should Stay Local By Default

Keep these on the user's device unless a future opt-in sync feature explicitly says otherwise:

- raw browser history
- raw local file contents
- raw context snippets
- local interest graph
- local source items
- local signal generation cache
- feedback events that are not needed for account billing or aggregate product telemetry
- sensitive URLs
- local file paths
- private exported conversation text
- API tokens and local credentials

## B. Data That Can Go To Cloud

Allowed cloud data, when necessary:

- user id
- device id
- subscription status
- entitlement checks
- anonymized usage events
- app version
- crash/error metadata without raw personal content
- optional synced settings
- opt-in summary-level interest profile
- billing provider ids
- license/session metadata

## C. Data That Should Not Be Sent By Default

Do not send by default:

- full local file text
- full browser visit history
- private document contents
- raw private conversation exports
- sensitive URLs
- tokens
- local paths
- source raw JSON containing private context

If the product later adds cloud sync, it must be opt-in and scoped.

## D. Privacy UX Principles

- Explain personal context use during onboarding.
- Make connectors opt-in.
- Let users turn connectors off any time.
- Let users delete local context data.
- Clearly say that full raw local files and browser history are not uploaded by default.
- Separate "local personalization" from "cloud account".
- Make future cloud sync optional.
- Provide a visible data/location explanation before asking for local folder access.

## E. API Cost And Copyright Risk Principles

External source handling:

- Do not copy full source articles into LUMOS.
- Preserve source links.
- Use short summaries and signal-level commentary.
- Respect source-specific API policies and rate limits.
- Cache and deduplicate source items.
- Keep source usage measurable.

Cost control:

- Meter source calls.
- Meter cloud AI usage if added later.
- Tie expensive features to Pro or Team entitlements.
- Add rate limits per user/device.
- Monitor failed source calls.

Copyright/product copy:

- Present LUMOS as a briefing and signal selection product, not a republication service.
- Keep original links visible.
- Avoid exposing long verbatim excerpts.
- Keep source attribution in details.

## F. Default Product Stance

LUMOS should sell trust as part of the product:

```text
개인 맥락은 로컬에서 먼저 처리하고, 클라우드에는 계정과 구독에 필요한 최소 정보만 보냅니다.
```

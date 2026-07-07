# Landing, Pricing, Legal Plan

Date: 2026-06-30

## A. Landing Page Structure

Recommended structure:

1. Hero
2. Problem definition
3. How LUMOS works
4. Product screenshots
5. Target users
6. Pricing
7. Download
8. FAQ
9. Privacy/security
10. Contact/support

The landing website should sell the outcome, not the pipeline.

## B. Core Messages

- 더 많은 정보가 아니라, 오늘 봐야 할 신호만
- 영어 원문도 한국어 브리핑으로
- 내 관심사와 작업 맥락 기반
- 검색하지 않아도 먼저 도착
- 개인 데이터는 로컬 우선
- 원문 링크와 출처는 유지

Avoid:

- "모든 트렌드를 실시간 추적"
- "완전 자동화"
- "모든 정보를 수집"
- "AI가 알아서 다 해줌"

## C. Pricing Draft

### Free

- limited daily signals
- basic sources
- manual refresh limit
- short history
- limited context connectors

### Pro

Draft price:

```text
월 9,900원
```

Possible Pro value:

- more daily signals
- automatic briefing
- expanded context connectors
- longer history
- advanced source controls
- higher usage limits

### Team

Future only:

- team workspace
- shared briefing
- member management
- team billing
- admin settings

Do not implement Team until individual Pro retention is validated.

## D. Legal Preparation

Required documents:

- privacy policy
- terms of service
- copyright/source content policy
- source attribution policy
- data deletion policy
- connector permission explanation
- refund/cancellation policy if billing exists

Privacy policy must explain:

- local-first architecture
- which data stays local
- which data may be sent to cloud
- opt-in connectors
- data deletion
- account and billing data

Copyright/source policy must explain:

- LUMOS summarizes and links to sources
- source links are preserved
- full source copying is not the product intent
- source terms should be respected

## E. Risks To Review Before Commercial Launch

- external source terms
- crawling/API usage policy
- summary copyright risk
- personal data handling
- payment/refund obligations
- consumer protection requirements
- storing auth tokens locally
- crash telemetry privacy

## F. Landing Page Non-Goals For MVP

- no fake testimonials
- no unsupported claims
- no enterprise security claims before implementation
- no paid checkout before billing infrastructure exists

## G. Landing Validation Guardrails

Landing pages must not imply that unimplemented features already exist.

Avoid:

- active payment wording before billing exists
- "download now" when there is no installer
- production login claims before production auth
- enterprise security claims before review
- full automation claims
- source coverage claims that collectors do not support

Required notices:

- current stage is local MVP / beta preparation
- Pro price is a validation hypothesis
- payment and signup are not live
- personal context follows a local-first principle
- source links and attribution are preserved
- refund/cancellation policy must be finalized before billing

Beta/price validation pages may ask users to express interest, but must not
collect email through an unimplemented backend. Use manual contact or disabled
CTA until a proper signup flow exists.

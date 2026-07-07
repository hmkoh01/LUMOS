# Next Priorities After User Test

Date: 2026-06-30

## Purpose

Use this document after demo sessions and user tests to decide what to build next. Do not prioritize by what is technically interesting first. Prioritize by where users fail to understand value or complete the first useful session.

## Priority Rules

### If Users Do Not Understand What LUMOS Does

Signal:

- They describe it as a news list.
- They ask "so is this just RSS?"
- They do not mention personal relevance or signal selection.

Priority:

1. Improve first-run headline and empty state copy.
2. Improve demo/landing explanation inside Web UI.
3. Clarify "today's signals" vs "news feed".

Do not start with:

- more collectors
- more settings
- tray/background work

### If Users Get Stuck During First Run

Signal:

- They cannot find `시작하기`.
- They do not know what keywords to enter.
- They visit settings before onboarding.

Priority:

1. Onboarding UX improvement.
2. Better keyword suggestions.
3. Stronger first-run CTA.
4. Fewer visible settings for first-time users.

### If Users Say Cards Are Too Long

Signal:

- They skim only title.
- They do not read `왜 중요한가`.
- They say three cards feel heavy.

Priority:

1. Signal card density improvement.
2. Progressive disclosure for secondary sections.
3. Stronger one-line signal summary.
4. Better section hierarchy.

### If Korean Briefing Feels Awkward

Signal:

- Users say the copy feels translated.
- Users cannot tell what the original item means.
- `왜 중요한가` feels generic.

Priority:

1. Korean briefing fixture tests.
2. Rule-based generator pattern improvements.
3. Source-specific copy templates.
4. Later: evaluate LLM-assisted summarization only after UX value is validated.

### If Signals Are Not Useful

Signal:

- Users understand the product but do not care about the cards.
- Recommendations feel too broad.
- Personalization does not feel real.

Priority:

1. Ranking calibration.
2. Interest matching improvements.
3. Source clustering/deduplication.
4. Better reason generation based on interests.

### If Feedback Buttons Are Confusing

Signal:

- Users cannot choose between `저장` and `계속 추적`.
- Users expect `관심 없음` to hide the card immediately.
- Users do not notice toast feedback.

Priority:

1. Button copy and microcopy.
2. Immediate visual state after feedback.
3. Short explanation in details or tooltip if needed.

### If Users Like The Value But Say Running It Is Annoying

Signal:

- They say they would use it if it just appeared.
- They dislike running a command.
- They understand Companion but do not want to keep a window open.

Priority:

1. Tray/background/notification design.
2. Startup behavior exploration.
3. Desktop Companion reduction.
4. Installer strategy later, not immediately.

### If Users Are Concerned About Personal Data

Signal:

- They worry about browser history.
- They do not want to connect local folders.
- They ask what is stored.

Priority:

1. Privacy explanation UX.
2. Local-only data handling documentation.
3. Clear connector toggles.
4. Data preview/delete controls only if needed.

### If Paid Intent Is Low

Signal:

- Users say it is nice but not worth paying.
- They cannot name a daily use case.
- They would only use it occasionally.

Priority:

1. Revisit target persona.
2. Narrow use case around stronger pain.
3. Improve signal usefulness before monetization.
4. Avoid pricing/plan work.

## Decision Matrix

| User Test Result | Next Priority | Defer |
| --- | --- | --- |
| Companion is confusing | Reduce Companion role or move toward tray/background | New collectors |
| Card feels long | Signal card density polish | More settings |
| Korean copy is awkward | Korean briefing quality fixtures | Payment |
| Signals are irrelevant | Ranking and matching calibration | Installer |
| First-run fails | Onboarding UX | Desktop polish |
| Users want daily passive delivery | Notification/tray exploration | More source management |
| Data concerns are high | Privacy UX and local data explanation | More personal context connectors |
| Low paid intent | Persona/use case validation | Pricing implementation |

## Recommended Next Phase Candidates

Choose based on the strongest user-test evidence:

1. `Signal Card Density & Briefing Copy Polish`
2. `Onboarding Conversion Fix Pass`
3. `Ranking Calibration & Source Clustering`
4. `Privacy Trust Layer`
5. `Desktop Passive Delivery Prototype`

## Rule

Do not build the next feature because it is missing from the roadmap. Build the next fix where users fail to get value.

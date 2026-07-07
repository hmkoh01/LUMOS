# User Test Script

Date: 2026-06-30

## Goal

Use this script to learn whether first-time users understand LUMOS and can reach their first Korean briefing without developer help.

Validate:

- whether users understand the core value
- where first-run onboarding breaks down
- whether Signal cards are readable
- whether Korean briefing copy feels natural
- whether `저장`, `관심 없음`, `계속 추적` are clear
- whether Companion is understood as a local helper, not the main app

## Target Participants

Recommended participants:

- 예비 창업자
- 대학생/대학원생
- 주니어 PM
- 콘텐츠 기획자
- AI/스타트업 트렌드를 자주 보는 사람

Session length:

- 20-30 minutes per participant

Setup:

- Use 1366x768 or 1440x900.
- Start from clean DB or prepared demo DB.
- Keep fallback demo data ready.
- Ask the participant to think aloud.

## Moderator Intro

Read:

```text
오늘은 완성된 상용 서비스를 평가하는 자리가 아니라, 로컬 MVP의 첫 사용 경험을 확인하는 자리입니다. 정답은 없고, 헷갈리는 부분이 있으면 그대로 말해주시면 됩니다.
```

Do not explain the product in detail before the task. Let the user infer the purpose from the UI.

## A. Pre-Test Questions

1. 평소 트렌드, 뉴스, 업계 정보를 어디서 확인하나요?
2. 하루에 정보 탐색에 대략 얼마나 시간을 쓰나요?
3. 너무 많은 정보 때문에 피로감을 느끼나요?
4. 어떤 주제의 신호를 매일 받고 싶나요?
5. 영어 원문 자료를 볼 때 어떤 점이 가장 불편한가요?
6. 매일 아침 짧은 개인 브리핑이 온다면 어떤 조건에서 유용할까요?

## B. Tasks

### Task 1. First Run

Prompt:

```text
LUMOS를 처음 실행했다고 생각하고 시작해보세요.
```

Observe:

- Does the user notice `시작하기`?
- Does the user understand Companion's role?
- Does the user try to use settings before onboarding?

### Task 2. Onboarding

Prompt:

```text
본인에게 맞게 역할과 관심사를 입력해보세요.
```

Expected:

- Select or enter a role.
- Add at least one keyword.
- Ideally add three or more keywords.
- Continue to settings without needing explanation.

Observe:

- Does comma/enter tag input feel natural?
- Are placeholder examples helpful?
- Does the privacy copy create concern?

### Task 3. Generate Signals

Prompt:

```text
오늘의 신호를 받아보세요.
```

Expected:

- User finds `오늘의 신호 받기`.
- Button enters busy state.
- User waits for result.
- Signals appear in the today tab.

Observe:

- Does the user understand what will happen?
- Is the waiting state clear?
- Is failure copy understandable if generation fails?

### Task 4. Read Signal Cards

Prompt:

```text
카드 3개를 읽고 가장 유용해 보이는 신호를 하나 골라보세요.
```

Ask while reading:

- 제목만 보고 어떤 신호인지 이해되나요?
- 요약이 자연스럽나요?
- 왜 중요한지 납득되나요?
- 왜 나에게 추천됐는지 개인화처럼 느껴지나요?
- 다음에 볼 것이 실제 행동으로 이어지나요?

Observe:

- Is the card too long?
- Does the user skip sections?
- Does the user look for original source?

### Task 5. Details And Source

Prompt:

```text
원문 정보를 찾아보세요.
```

Expected:

- User opens `자세히 보기`.
- User sees original title/snippet.
- User understands `원문 보기`.

Observe:

- Does details feel too technical?
- Does original English overwhelm the card?

### Task 6. Feedback

Prompt:

```text
이 신호에 대해 저장, 관심 없음, 계속 추적 중 하나를 눌러보세요.
```

Observe:

- Which action do they choose?
- Do they understand the difference?
- Is toast feedback noticed?
- Do they expect the card to disappear or remain?

### Task 7. Find Settings And Activity

Prompt:

```text
설정 화면이나 활동 기록을 찾아보세요.
```

Observe:

- Does the navigation make sense?
- Do Companion buttons help or confuse?
- Does `/app#settings` or `/app#activity` feel like the same app?

## C. Observation Checklist

Mark each item:

| Item | Pass / Partial / Fail | Notes |
| --- | --- | --- |
| Finds `시작하기` quickly |  |  |
| Understands what LUMOS does |  |  |
| Completes onboarding without help |  |  |
| Adds keywords successfully |  |  |
| Understands `오늘의 신호 받기` |  |  |
| Reads Signal card without fatigue |  |  |
| Korean summary feels natural |  |  |
| Recommendation reason feels personal |  |  |
| Finds original source details |  |  |
| Understands feedback buttons |  |  |
| Notices toast/status feedback |  |  |
| Finds settings/activity |  |  |
| Understands Companion as helper |  |  |

## D. Post-Test Questions

1. 이 서비스가 무엇을 해주는 앱인지 한 문장으로 설명해본다면?
2. 오늘의 신호 3개가 유용했나요?
3. 이걸 매일 받아보고 싶나요?
4. 어떤 주제라면 계속 쓰고 싶나요?
5. 어떤 부분이 가장 헷갈렸나요?
6. 카드가 너무 길거나 짧았나요?
7. `왜 나에게 추천됐나요?`가 개인화처럼 느껴졌나요?
8. `저장`, `관심 없음`, `계속 추적` 버튼의 의미가 명확했나요?
9. 영어 원문 자료를 한국어로 보여주는 방식이 도움이 됐나요?
10. Companion 창의 역할이 이해됐나요?
11. 월 9,900원을 낼 가능성이 있나요? 있다면 어떤 조건에서인가요?
12. 다른 사람에게 추천할 만한가요?

## E. Evaluation Criteria

Use these criteria after each session:

| Criteria | Strong Signal | Weak Signal |
| --- | --- | --- |
| Core value understanding | User says it reduces what to read today | User says it is just a news list |
| First-run success | Completes onboarding without help | Gets stuck before signals |
| Card comprehension | Can explain one signal back | Cannot identify why it matters |
| Korean briefing quality | Says wording is natural | Says it feels translated or vague |
| Personalization | Understands recommendation reason | Says it feels generic |
| Feedback clarity | Knows when to use each button | Buttons feel ambiguous |
| Reuse intent | Wants daily signal delivery | Treats it as one-time curiosity |
| Paid intent | Can name a condition for payment | No clear value or target use |

## Session Notes Template

```text
Participant:
Persona:
Date:

Pre-test summary:

Task results:
- First run:
- Onboarding:
- Signal generation:
- Card reading:
- Details/source:
- Feedback:
- Settings/activity:

Best quote:

Most confusing moment:

Top improvement:

Reuse intent:
Paid intent:
```

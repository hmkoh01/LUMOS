# Auth UI Wireframe

Date: 2026-07-05

## Purpose

Design future account and device authentication surfaces without implementing them in the current local MVP.

## First Launch Options

Future first screen may offer:

- `무료로 시작하기`
- `로그인`
- `나중에 하기`

Recommended default:

- allow local-first trial without forcing login immediately
- explain that login enables sync, subscription, and device registration

## Login Screen

Fields:

- email
- password or OAuth provider button in a later phase

Actions:

- login
- create account
- forgot password

Do not implement password handling in the local app.

## After Login

Flow:

1. validate session
2. register device
3. fetch entitlement
4. continue onboarding or today's signals

Copy:

```text
이 기기에서 LUMOS를 사용할 수 있게 연결했어요.
```

## Device Registration Complete

Screen elements:

- device name
- plan
- last checked time
- button: `오늘의 신호로 이동`

## Subscription Status

Possible states:

- Free
- Pro
- Team
- inactive
- offline grace
- expired

Copy examples:

- `현재 Free 요금제를 사용 중이에요.`
- `Pro 기능을 사용할 수 있어요.`
- `구독 상태를 확인하려면 인터넷 연결이 필요해요.`

## Entitlement Denied

Copy:

```text
현재 요금제에서는 사용할 수 없는 기능이에요.
필요하면 Pro 요금제로 업그레이드할 수 있어요.
```

UX rule:

- do not block access to existing local data

## Offline Grace

Copy:

```text
인터넷 연결이 불안정해요. 최근 확인한 구독 상태를 기준으로 계속 사용할게요.
```

## Companion Account State

Future Companion status can show:

- `로그인됨`
- `로그인 필요`
- `구독 확인 중`
- `오프라인 사용 중`

Keep it subtle. Companion should remain a local helper, not the full account center.

## Web UI Account Placement

Future Web UI can add:

- a small account area in the sidebar
- a future `계정` tab
- plan badge near settings

Do not add this UI until auth backend decisions are made.

## Current MVP Rule

The current MVP remains usable without login. This wireframe is for future productization only.

## Implemented Local Account Shell

Current implementation:

- Web UI settings tab includes a `계정` section.
- Sidebar shows a small `로컬 모드` chip.
- Companion status area shows `계정: 로컬 모드`.
- No login is required.
- No cloud backend is called.
- No token is stored.

Settings account section shows:

- current state: local mode
- account connection: not signed in
- device state: running on this device, not registered
- plan state: local MVP, future Free / Pro / Team connection planned

Buttons:

- `개발용 Cloud 연결 테스트`
- `개발용 연결 해제`
- `사용량 이벤트 테스트`
- `계정 구조 보기`
- `제품화 로드맵 보기`

These are shell actions only. They must not look like real signup/login.

## Mock Auth Display Rule

For development/QA only, Web UI can read:

```text
?mockAuth=free
?mockAuth=pro
```

Display examples:

- `Mock Free 계정`
- `Mock Pro 계정`

Rules:

- must clearly say it is a mock state
- must not imply real login
- must not enable billing or gated features
- must not call `/api/v1/auth/*`

## Implemented Local Cloud Dev Connection

The Settings account shell can now call local development bridge endpoints:

- `GET /api/v1/product/cloud/status`
- `POST /api/v1/product/cloud/dev-connect`
- `POST /api/v1/product/cloud/dev-disconnect`
- `GET /api/v1/product/cloud/account`
- `POST /api/v1/product/cloud/usage-test`

The bridge then talks to the development cloud backend. This is opt-in and does
not make the Web UI login-required.

UI principles:

- local mode remains the default
- dev cloud connection is explicitly labeled as development-only
- no token is displayed in the browser
- cloud-off errors are shown only in the account shell
- the rest of LUMOS remains usable without the cloud backend

## Future Signed-In State

Future real signed-in state should show:

- account email
- device registration status
- plan
- entitlement summary
- last subscription check time

This should be wired only after real cloud auth exists.

## Why Login Is Not Required Yet

Local-first use is core to LUMOS. Requiring login before the product value is validated would add friction and weaken the privacy story. The current app must continue to work in local mode.

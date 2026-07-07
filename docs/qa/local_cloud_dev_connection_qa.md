# Local Cloud Dev Connection QA

This QA note verifies the opt-in development connection between the local LUMOS
app and the development cloud auth backend.

## Scope

- Local mode remains the default.
- The Web UI is not login-required.
- The cloud backend is contacted only when the user clicks the development
  connection test button in Settings.
- Dev tokens are kept in local app memory only.
- No production login, OAuth, password auth, billing, or secure token storage is
  implemented in this phase.

## Run

Start the development cloud backend:

```powershell
python run.py cloud
```

Start the local app:

```powershell
python run.py app
```

Or use Companion:

```powershell
python run.py companion
```

Open:

```text
http://127.0.0.1:8000/app#settings
```

## Expected Default State

- Account section shows local mode.
- Cloud status says it is not connected.
- The app remains usable even if `python run.py cloud` is not running.

## Dev Connection Test

Click `개발용 Cloud 연결 테스트`.

Expected flow:

1. local bridge checks cloud `/health`
2. local bridge calls cloud `/auth/dev-login`
3. local bridge calls cloud `/auth/me`
4. local bridge calls cloud `/devices/register`
5. local bridge calls cloud `/entitlements/me`
6. Settings account section shows development cloud connection state

Expected UI:

- mode: development cloud connected
- user email: `demo@lumos.local`
- device status: `active`
- plan: `pro`
- entitlement summary appears
- entitlement cache status appears
- grace expiry appears
- no token is shown in the browser

## Usage Event Test

Click `사용량 이벤트 테스트`.

Expected:

- local bridge sends `dev_connection_test`
- metadata only includes non-sensitive surface information
- no browser history, local file text, token, URL list, or personal context raw
  text is sent

## Disconnect Test

Click `개발용 연결 해제`.

Expected:

- bridge attempts cloud logout
- in-memory dev state is cleared
- account section returns to local mode

## Cloud-Off Error

Stop the cloud backend and click `개발용 Cloud 연결 테스트`.

Expected:

- friendly message: `Cloud backend가 실행 중인지 확인해 주세요: python run.py cloud`
- local mode remains usable
- the rest of the Web UI does not fail

## Local Bridge Endpoints

- `GET /api/v1/product/cloud/status`
- `POST /api/v1/product/cloud/dev-connect`
- `POST /api/v1/product/cloud/dev-disconnect`
- `GET /api/v1/product/cloud/account`
- `POST /api/v1/product/cloud/usage-test`

These are development bridge endpoints, not production auth endpoints.

# Windows Portable Build Plan

## 목적

Closed beta 사용자에게 Python 설치 없이 실행 가능한 LUMOS prototype을 전달하기 위한 Windows portable build 전략을 정리한다.

이번 단계는 installer가 아니다. code signing, auto-update, OS startup/tray는 구현하지 않는다.

## 왜 portable build부터 가는가

- closed beta에서는 설치 마찰보다 실행 가능성 검증이 우선이다.
- installer 제작 전 resource path, DB 위치, Companion 실행 흐름을 검증해야 한다.
- zip으로 수동 전달하면 cohort별 build를 통제하기 쉽다.
- 문제가 생겼을 때 실행 폴더와 `data/`를 함께 확인하기 쉽다.

## Packaging 방식

우선 방식: PyInstaller `onedir`

선택 이유:

- static file과 landing page 포함 여부를 확인하기 쉽다.
- resource path 문제를 디버깅하기 쉽다.
- 실행 파일 옆 `data/` 폴더 정책을 검증하기 쉽다.
- closed beta zip 구조를 만들기 쉽다.

`onefile`은 나중에 검토한다. 초기에는 압축 해제와 임시 폴더 동작 때문에 resource path와 보안 경고를 추적하기 어려울 수 있다.

## Build entrypoint

Portable entrypoint:

```text
src/app/portable_entry.py
```

동작:

1. portable data directory를 준비한다.
2. version 정보를 console에 출력한다.
3. 기존 `run.py companion` 흐름을 재사용한다.
4. Companion이 local FastAPI server를 확인/시작한다.
5. 브라우저에서 `/app#today`를 연다.

Cloud backend는 자동 실행하지 않는다.

## Runtime resource

포함해야 할 resource:

- `src/web/static/*`
- `src/web/landing/*`
- `packaging/windows/beta_package/*.md`
- Python runtime dependency
- SQLite runtime
- tkinter runtime

포함하지 않을 것:

- installer asset
- code signing material
- auto-update metadata
- font 파일
- demo DB
- 사용자 DB

## Data directory

Portable beta prototype 기본값:

```text
<executable folder>/data/
```

정책:

- 일반 DB: `data/lumos.db`
- demo DB: `data/demo_lumos.db`는 demo mode에서만 사용
- cloud DB: cloud backend를 별도로 실행할 때만 사용
- `LUMOS_DB_PATH`는 기존처럼 특정 DB 파일 override에 사용한다.
- `LUMOS_DATA_DIR`은 portable prototype에서 data root override에 사용할 수 있다.

향후 installer 단계에서는 `%APPDATA%/LUMOS` 같은 OS 표준 app data 경로를 다시 검토한다.

## Package structure

예상 구조:

```text
LUMOS/
  LUMOS.exe
  data/
  README_FIRST.md
  RELEASE_NOTES.md
  KNOWN_ISSUES.md
  PRIVACY_NOTES.md
  FEEDBACK_GUIDE.md
```

## Build files

```text
packaging/windows/build_portable.ps1
packaging/windows/build_portable.py
packaging/windows/lumos_portable.spec
packaging/windows/README.md
packaging/windows/beta_package/
```

## Execution QA result

Windows Portable Build Execution QA에서 실제 artifact 생성을 확인했다.

Build prerequisite:

- Python 3.9.21
- PyInstaller 6.21.0

Generated artifacts:

```text
dist/LUMOS/
dist/LUMOS-0.1.0-alpha-portable.zip
```

Packaging fixes applied:

- workspace-local `.build_home` for PyInstaller home path issues
- absolute portable entrypoint path in spec
- PyQt/PySide exclusions because LUMOS does not use Qt
- manual Tcl/Tk inclusion for tkinter Companion
- direct FastAPI app object handoff to uvicorn inside packaged Companion server startup

## 예상 리스크

- PyInstaller hidden import 누락
- tkinter runtime 누락
- FastAPI static mount resource path 오류
- Windows 보안 경고
- antivirus false positive
- 브라우저 자동 열기 실패
- 실행 폴더 권한 문제
- port 8000 충돌

## Installer/code signing으로 넘어갈 조건

- portable build가 Windows 10/11에서 안정적으로 실행된다.
- `/app`, `/pricing`, `/download`, `/beta` route가 packaged build에서 동작한다.
- first-run onboarding과 signal generate가 동작한다.
- data persistence와 삭제 안내가 검증된다.
- closed beta 사용자 3~5명에게 설치/실행 치명 문제가 없다.
- code signing 비용과 배포 채널을 결정한다.

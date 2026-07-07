# Windows Portable Build QA

## Purpose

Verify that the LUMOS closed beta portable build can be created and run on Windows without requiring users to type `python run.py companion`.

This QA does not validate installer, code signing, auto-update, OS startup, tray behavior, payment, signup, or production cloud login.

## Environment

- OS: Windows 10 / build 10.0.26200
- Python: 3.9.21
- pip: 25.2
- PyInstaller: 6.21.0
- Build channel: alpha
- App version: 0.1.0-alpha
- Build stage: closed_beta_prototype

PyInstaller was not initially installed. It was installed as a build tool only with:

```powershell
pip install pyinstaller
```

## Build Command

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build_portable.ps1
```

## Build Result

Status: succeeded after packaging fixes.

Artifacts:

```text
dist/LUMOS/
dist/LUMOS-0.1.0-alpha-portable.zip
```

Observed package structure:

```text
dist/LUMOS/
  LUMOS.exe
  data/
  _internal/
  README_FIRST.md
  RELEASE_NOTES.md
  KNOWN_ISSUES.md
  PRIVACY_NOTES.md
  FEEDBACK_GUIDE.md
```

Zip artifact was generated:

```text
dist/LUMOS-0.1.0-alpha-portable.zip
```

## Issues Found And Fixed

### 1. PyInstaller home path permission failure

Symptom:

```text
PermissionError: [WinError 5] Access is denied: 'C:\\Users\\koh'
```

Fix:

- `packaging/windows/build_portable.ps1` now sets `HOME` and `USERPROFILE` to workspace-local `.build_home`.
- The script invokes `python -m PyInstaller` instead of relying on PATH script resolution.

### 2. Spec root path failure

Symptom:

```text
script '...\\packaging\\windows\\src\\app\\portable_entry.py' not found
```

Fix:

- `lumos_portable.spec` now searches upward for `src/app/portable_entry.py`.
- Analysis entrypoint now uses an absolute path.

### 3. PyQt5/PyQt6 hook conflict from build environment

Symptom:

```text
attempt to collect multiple Qt bindings packages
```

Fix:

- PyQt5, PyQt6, PySide2, PySide6 and unrelated analysis-heavy packages are excluded in the spec.
- LUMOS does not use Qt for this build.

### 4. tkinter missing in packaged executable

Symptom:

```text
ModuleNotFoundError: No module named 'tkinter'
```

Fix:

- `_tkinter.pyd`, Tcl/Tk DLLs, Tcl/Tk data, and tkinter stdlib files are explicitly included.
- A runtime hook sets `TCL_LIBRARY` and `TK_LIBRARY`.

### 5. Packaged uvicorn ASGI string import failure

Symptom:

```text
Error loading ASGI app. Could not import module "src.app.main".
```

Fix:

- `src/app/server_control.py` now passes the FastAPI app object directly to `uvicorn.Config` when starting the local server from Companion.

## Packaged App Execution QA

Command:

```powershell
dist/LUMOS/LUMOS.exe
```

Result:

- Process stayed alive.
- Local FastAPI server started.
- Browser route checks passed.
- Companion GUI was started in hidden automation mode for QA. A visible manual UI check is still recommended before sending to external beta testers.

## Route QA

Packaged app route results:

| Route | Result |
| --- | --- |
| `/health` | 200 |
| `/app` | 200 |
| `/` | 200 |
| `/pricing` | 200 |
| `/download` | 200 |
| `/beta` | 200 |
| `/static/app.js` | 200 |
| `/landing-static/landing.js` | 200 |

## Product Flow QA

Performed through packaged local server with isolated `LUMOS_DATA_DIR`.

Results:

- First-run state detected: `onboarding_completed = false`
- Signal generation: 3 signals generated
- Today signal count: 3
- Feedback event: saved
- Reopen persistence: 3 signals remained after close/reopen
- Cloud backend: not required
- Local mode: maintained

Manual browser click QA still recommended:

- Onboarding Step 1/2/3
- Signal details open
- Settings/account shell
- Interests/sources/activity tab navigation
- Visible Companion window layout

## Data Persistence QA

Tested with:

```powershell
$env:LUMOS_DATA_DIR="C:\\Users\\koh\\AppData\\Local\\Temp\\LUMOS_PORTABLE_QA_<id>"
dist/LUMOS/LUMOS.exe
```

Observed:

- `lumos.db` created in the configured data directory.
- Signals persisted after close/reopen.
- Feedback status persisted.
- Cloud backend was not required.

Cleanup:

```powershell
Remove-Item Env:LUMOS_DATA_DIR
```

For beta users, data deletion is still documented as deleting the executable folder's `data/` directory after closing the app.

## Zip Package QA

Checked:

- `LUMOS.exe` exists.
- beta package markdown docs exist.
- `data/` folder exists.
- `src/web/static` and `src/web/landing` resources are included under `_internal`.
- No `.env`, token prefix, local DB, demo DB, or cloud DB was found in the generated package scan.

Generated QA output files such as `run_stdout.txt` and `run_stderr.txt` are not part of the generated zip and should not be included in a manual re-zip.

## Security Warning QA

Not fully verified.

Notes:

- No code signing is present.
- Windows SmartScreen or antivirus warnings may appear.
- This must be recorded during visible manual execution on the target beta machine.

## Beta Readiness Judgment

Judgment: Almost ready.

Reason:

- Build artifact and zip are generated.
- Packaged local server routes work.
- Generate/feedback/persistence work through packaged server.
- Remaining requirement before external beta: visible Companion/browser manual QA on a clean Windows 10/11 machine and SmartScreen/antivirus warning recording.

## Remaining Risks

- The build environment is Anaconda-based and required Tcl/Tk manual packaging fixes.
- The generated onedir package may include extra conda runtime modules. Size and dependency pruning should be reviewed before external distribution.
- Visible Companion layout was not manually inspected in this automated QA pass.
- No code signing means warnings are expected.

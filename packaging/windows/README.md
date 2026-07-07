# LUMOS Windows Portable Build

This folder contains the closed beta portable build prototype.

## Strategy

- Build type: PyInstaller `onedir`
- Executable name: `LUMOS`
- Entrypoint: `src.app.portable_entry`
- Distribution target: manual closed beta zip

This is not an installer. It does not include code signing, auto-update, OS startup registration, or tray behavior.

## Build

From the project root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build_portable.ps1
```

The script checks for PyInstaller and stops with a clear message if it is not installed.

Build prerequisite:

```powershell
pip install pyinstaller
```

The script sets `HOME` and `USERPROFILE` to a workspace-local `.build_home` folder during build to avoid Windows home path permission issues observed in some managed environments.

## Expected Output

```text
dist/LUMOS/
  LUMOS.exe
  data/
  README_FIRST.md
  RELEASE_NOTES.md
  KNOWN_ISSUES.md
  PRIVACY_NOTES.md
  FEEDBACK_GUIDE.md
```

## Notes

- Static Web UI files are bundled from `src/web/static`.
- Landing pages are bundled from `src/web/landing`.
- Beta package documents are bundled from `packaging/windows/beta_package`.
- Runtime data is expected under the executable folder's `data/` directory for the portable prototype.
- Tcl/Tk resources are manually included for the tkinter Companion window.

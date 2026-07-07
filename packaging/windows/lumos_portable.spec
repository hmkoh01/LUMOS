# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


def find_project_root():
    candidates = [Path.cwd().resolve(), Path(SPECPATH).resolve()]
    for candidate in list(candidates):
        candidates.extend(candidate.parents)
    for candidate in candidates:
        if (candidate / "src" / "app" / "portable_entry.py").exists():
            return candidate
    raise RuntimeError("Could not find project root for LUMOS portable build")


ROOT = find_project_root()
PY_ROOT = Path(sys.base_prefix)

datas = [
    (str(ROOT / "src" / "web" / "static"), "src/web/static"),
    (str(ROOT / "src" / "web" / "landing"), "src/web/landing"),
    (str(ROOT / "packaging" / "windows" / "beta_package"), "packaging/windows/beta_package"),
    (str(PY_ROOT / "Library" / "lib" / "tcl8.6"), "_tcl_data"),
    (str(PY_ROOT / "Library" / "lib" / "tk8.6"), "_tk_data"),
    (str(PY_ROOT / "Lib" / "tkinter"), "tkinter"),
]

binaries = [
    (str(PY_ROOT / "DLLs" / "_tkinter.pyd"), "."),
    (str(PY_ROOT / "Library" / "bin" / "tcl86t.dll"), "."),
    (str(PY_ROOT / "Library" / "bin" / "tk86t.dll"), "."),
]

hiddenimports = [
    "tkinter",
    "_tkinter",
    "uvicorn",
    "fastapi",
    "sqlite3",
]

excludes = [
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "IPython",
    "jupyter",
    "notebook",
    "sphinx",
    "matplotlib",
    "numpy",
    "pandas",
    "PIL",
    "black",
    "yapf",
]

a = Analysis(
    [str(ROOT / "src" / "app" / "portable_entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "packaging" / "windows" / "pyi_rth_tk.py")],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LUMOS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LUMOS",
)

from pathlib import Path
import shutil
import zipfile


ROOT = Path(__file__).resolve().parents[2]
DIST_DIR = ROOT / "dist" / "LUMOS"
PACKAGE_DOCS = ROOT / "packaging" / "windows" / "beta_package"
ZIP_PATH = ROOT / "dist" / "LUMOS-0.1.0-alpha-portable.zip"


def copy_beta_docs() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    for path in PACKAGE_DOCS.glob("*.md"):
        shutil.copy2(path, DIST_DIR / path.name)


def ensure_data_dir() -> None:
    (DIST_DIR / "data").mkdir(parents=True, exist_ok=True)


def remove_packaging_noise() -> None:
    tkinter_dir = DIST_DIR / "_internal" / "tkinter"
    tkinter_test_dir = tkinter_dir / "test"
    if tkinter_test_dir.exists():
        shutil.rmtree(tkinter_test_dir)
    for cache_dir in tkinter_dir.rglob("__pycache__"):
        shutil.rmtree(cache_dir)


def ensure_executable() -> None:
    exe = DIST_DIR / "LUMOS.exe"
    if not exe.exists():
        raise FileNotFoundError(f"Expected executable was not created: {exe}")


def make_zip() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in DIST_DIR.rglob("*"):
            archive.write(path, path.relative_to(DIST_DIR.parent))


def main() -> None:
    ensure_executable()
    copy_beta_docs()
    ensure_data_dir()
    remove_packaging_noise()
    make_zip()
    print(f"Prepared {DIST_DIR}")
    print(f"Prepared {ZIP_PATH}")


if __name__ == "__main__":
    main()

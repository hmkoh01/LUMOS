import os
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def packaged_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return project_root()


def bundled_root() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass).resolve() if meipass else project_root()


def web_static_dir() -> Path:
    return bundled_root() / "src" / "web" / "static"


def web_landing_dir() -> Path:
    return bundled_root() / "src" / "web" / "landing"


def docs_dir() -> Path:
    return bundled_root() / "docs"


def package_docs_dir() -> Path:
    return bundled_root() / "packaging" / "windows" / "beta_package"


def data_dir() -> Path:
    configured = os.environ.get("LUMOS_DATA_DIR")
    if configured:
        return Path(configured)
    return packaged_root() / "data"


def database_path(name: str = "lumos.db") -> Path:
    return data_dir() / name

import os
from pathlib import Path

from src.app.resource_paths import data_dir

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = data_dir()
DATABASE_PATH = DATA_DIR / "lumos.db"
DEMO_DATABASE_PATH = DATA_DIR / "demo_lumos.db"


def get_database_path() -> Path:
    configured = os.environ.get("LUMOS_DB_PATH")
    return Path(configured) if configured else DATABASE_PATH

API_HOST = "127.0.0.1"
API_PORT = 8000
DEFAULT_USER_ID = 1

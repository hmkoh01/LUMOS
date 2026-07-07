import os
from pathlib import Path


CLOUD_HOST = os.getenv("LUMOS_CLOUD_HOST", "127.0.0.1")
CLOUD_PORT = int(os.getenv("LUMOS_CLOUD_PORT", "8010"))

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLOUD_DB_PATH = PROJECT_ROOT / "data" / "cloud_lumos.db"
CLOUD_DB_PATH = Path(os.getenv("LUMOS_CLOUD_DB_PATH", str(DEFAULT_CLOUD_DB_PATH)))


from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.storage.sqlite_store import SQLiteStore


@dataclass
class Runtime:
    store: SQLiteStore


def create_runtime(db_path: Optional[Path] = None) -> Runtime:
    return Runtime(store=SQLiteStore(db_path))

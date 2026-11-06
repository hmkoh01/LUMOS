"""Explicit, idempotent Engine v2 wiring.  Never starts workers or schedules."""

from __future__ import annotations

import os
import math
from pathlib import Path
from typing import Any, Optional

from src.engine.config import EngineConfig
from src.engine.llm.cache import BriefingCache
from src.engine.llm.handlers import register_generate_briefing_handler
from src.engine.llm.providers import create_structured_provider
from src.engine.llm.service import EngineBriefingService
from src.engine.llm.structured_cache import StructuredBriefingCache


_bootstrapped: Optional[EngineBriefingService] = None


def engine_cache_path() -> Path:
    configured = os.environ.get("LUMOS_ENGINE_CACHE_DB_PATH", "").strip()
    if configured:
        return Path(configured)
    from src.app.config import DATA_DIR
    return DATA_DIR / "engine_briefings.sqlite"


def initialize_engine(store: Any, config: Optional[EngineConfig] = None) -> Optional[EngineBriefingService]:
    """Register the briefing handler only when Engine v2 is explicitly enabled."""
    global _bootstrapped
    cfg = config or EngineConfig.from_env()
    if not cfg.enabled:
        return None
    if _bootstrapped is not None:
        return _bootstrapped
    cache_path = engine_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    structured_cache = StructuredBriefingCache(cache_path)
    structured_cache.purge_older_than(max(1, math.ceil(cfg.llm.cache_ttl_hours / 24)))
    service = EngineBriefingService(create_structured_provider(cfg), BriefingCache(cache_path), structured_cache)
    register_generate_briefing_handler(service, store)
    _bootstrapped = service
    return service


def reset_engine_bootstrap_for_test() -> None:
    global _bootstrapped
    _bootstrapped = None

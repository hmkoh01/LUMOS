"""Periodic collection scheduler.

DISABLED BY DEFAULT.  Importing this module does not start any
background activity.  Call ``Scheduler.start()`` explicitly only after
verifying ``config.collection.scheduler_enabled is True``.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from src.engine.config import EngineConfig

logger = logging.getLogger(__name__)


class Scheduler:
    """Simple interval-based scheduler using a daemon thread."""

    def __init__(self, config: EngineConfig, run_fn: Callable[[], None]):
        self.config = config
        self._run_fn = run_fn
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def interval_seconds(self) -> int:
        return self.config.collection.schedule_interval_hours * 3600

    def start(self) -> None:
        """Start the scheduler if enabled.  No-op when disabled."""
        if not self.config.collection.scheduler_enabled:
            logger.info("Scheduler is disabled by configuration — not starting")
            return
        if not self.config.enabled:
            logger.info("Engine is disabled — scheduler will not start")
            return
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="engine-scheduler")
        self._thread.start()
        logger.info("Scheduler started (interval=%ds)", self.interval_seconds)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None
        logger.info("Scheduler stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    def run_once(self) -> None:
        """Execute the scheduled function once (for testing)."""
        self._run_fn()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._run_fn()
            except Exception:
                logger.exception("Scheduled run failed")
            self._stop_event.wait(timeout=self.interval_seconds)

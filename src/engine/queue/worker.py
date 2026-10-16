"""Worker pool for processing queued jobs.

Workers run in-process using threads (not multiprocessing) to keep the
deployment simple.  The pool respects ``max_concurrent_workers`` and
never starts automatically on import.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from src.engine.config import EngineConfig
from src.engine.models import JobStatus, JobType
from src.engine.queue.store import QueueStore
from src.engine.safety import ExternalCallBlocked, check_external_call_allowed

logger = logging.getLogger(__name__)

# Registry of job handlers keyed by job_type
JobHandler = Callable[[Dict[str, Any], EngineConfig], Dict[str, Any]]
_handlers: Dict[str, JobHandler] = {}


def register_handler(job_type: str, handler: JobHandler) -> None:
    _handlers[job_type] = handler


def get_handler(job_type: str) -> Optional[JobHandler]:
    return _handlers.get(job_type)


class WorkerPool:
    """Manages a fixed number of worker threads that drain the job queue."""

    def __init__(
        self,
        queue_store: QueueStore,
        config: EngineConfig,
        *,
        worker_id_prefix: str = "worker",
    ):
        self.queue = queue_store
        self.config = config
        self._prefix = worker_id_prefix
        self._stop_event = threading.Event()
        self._threads: List[threading.Thread] = []

    @property
    def max_workers(self) -> int:
        return self.config.collection.max_concurrent_workers

    def start(self) -> None:
        """Start worker threads.  Idempotent — does nothing if already running."""
        if self._threads:
            return
        self._stop_event.clear()
        for i in range(self.max_workers):
            wid = f"{self._prefix}-{i}"
            t = threading.Thread(target=self._worker_loop, args=(wid,), daemon=True, name=wid)
            self._threads.append(t)
            t.start()
        logger.info("WorkerPool started with %d workers", self.max_workers)

    def stop(self, timeout: float = 10.0) -> None:
        """Signal all workers to stop and wait for them."""
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=timeout)
        self._threads.clear()
        logger.info("WorkerPool stopped")

    def is_running(self) -> bool:
        return bool(self._threads) and not self._stop_event.is_set()

    def process_one(self, worker_id: str = "inline") -> bool:
        """Process a single job synchronously.  Returns True if a job was found."""
        self.queue.recover_expired_leases()
        job = self.queue.claim(worker_id, lease_seconds=300)
        if job is None:
            return False

        handler = get_handler(job.job_type)
        if handler is None:
            self.queue.fail(job.id, f"No handler for job_type={job.job_type}")
            return True

        try:
            result = handler(job.payload_json, self.config)
            self.queue.complete(job.id, result)
        except ExternalCallBlocked as exc:
            self.queue.fail(job.id, f"External call blocked: {exc}")
        except Exception as exc:
            logger.exception("Job %d failed: %s", job.id, exc)
            self.queue.fail(job.id, str(exc))
        return True

    def _worker_loop(self, worker_id: str) -> None:
        while not self._stop_event.is_set():
            try:
                did_work = self.process_one(worker_id)
            except Exception:
                logger.exception("Worker %s encountered an error", worker_id)
                did_work = False
            if not did_work:
                self._stop_event.wait(timeout=2.0)

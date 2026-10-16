"""Abstract job queue store interface.

Concrete implementations (SQLite now, Redis later) implement this
protocol so the rest of the engine is storage-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

from src.engine.models import Job, JobStatus


class QueueStore(ABC):
    """Persistent job queue with deduplication and atomic claiming."""

    @abstractmethod
    def enqueue(self, job: Job) -> Job:
        """Insert a job if no duplicate ``dedupe_key`` is pending/running.

        Returns the existing job when a duplicate is found, or the newly
        created job otherwise.
        """

    @abstractmethod
    def claim(self, worker_id: str, lease_seconds: int = 300) -> Optional[Job]:
        """Atomically claim the highest-priority pending job.

        Sets status to RUNNING, assigns ``lease_owner`` and
        ``lease_expires_at``.  Returns ``None`` when the queue is empty.
        """

    @abstractmethod
    def complete(self, job_id: int, result: Dict[str, Any]) -> None:
        """Mark a job as completed with its result."""

    @abstractmethod
    def fail(self, job_id: int, error: str) -> None:
        """Mark a job as failed.  Increments retry_count.

        If retry_count < max_retries the job is re-queued as pending.
        """

    @abstractmethod
    def cancel(self, job_id: int) -> None:
        """Cancel a pending or running job."""

    @abstractmethod
    def recover_expired_leases(self) -> int:
        """Re-queue jobs whose lease has expired.  Returns count recovered."""

    @abstractmethod
    def get_job(self, job_id: int) -> Optional[Job]:
        """Fetch a single job by id."""

    @abstractmethod
    def get_pending_count(self) -> int:
        """Number of pending jobs."""

    @abstractmethod
    def get_running_count(self) -> int:
        """Number of currently running jobs."""

    @abstractmethod
    def find_duplicate(self, dedupe_key: str) -> Optional[Job]:
        """Find an active (pending/running) job with the same dedupe key."""

    @abstractmethod
    def list_jobs(
        self,
        *,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Job]:
        """List jobs with optional filters."""

    @abstractmethod
    def purge_completed(self, older_than_hours: int = 72) -> int:
        """Delete completed/failed jobs older than threshold.  Returns count."""

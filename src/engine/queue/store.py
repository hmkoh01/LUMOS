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
    def enqueue_once(self, job: Job) -> Job:
        """Insert only once for a durable calendar/job dedupe key.

        Completed jobs also suppress a duplicate.  Scheduled work uses this
        variant so restarts and concurrent service instances cannot replay a
        completed collection slot.
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
    def defer(self, job_id: int, delay_seconds: float, reason: str = "") -> None:
        """Return a running dependency job to the queue until it is eligible."""

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
    def get_job_by_dedupe_key(self, dedupe_key: str) -> Optional[Job]:
        """Return the latest durable job for a calendar dedupe key, if any."""

    @abstractmethod
    def reserve_source_request(self, source_id: str, request_day: str, max_requests: int) -> bool:
        """Atomically reserve one source request from its global daily cap.

        The reservation is shared by every worker using the same queue store.
        A failed upstream call still consumes the slot so retry loops cannot
        bypass a no-cost operating ceiling.
        """

    @abstractmethod
    def get_source_request_usage(self, source_id: str, request_day: str) -> int:
        """Return the persisted number of reserved requests for a source/day."""

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

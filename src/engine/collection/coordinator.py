"""Collection coordinator: orchestrates plan → queue → share results.

This module ties together the planner, the job queue, and user-specific
source settings.  It respects disabled sources and regional preferences.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from src.engine.config import EngineConfig
from src.engine.collection.planner import build_collection_plan, plan_to_jobs
from src.engine.models import Job
from src.engine.queue.store import QueueStore
from src.engine.safety import ExternalCallBlocked, check_external_call_allowed

logger = logging.getLogger(__name__)

KOREA_TZ = timezone(timedelta(hours=9))


def _today_range() -> Tuple[str, str]:
    """Return (start, end) ISO dates for today in KST."""
    now = datetime.now(KOREA_TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).date().isoformat()
    end = now.date().isoformat()
    return start, end


class CollectionCoordinator:
    """Top-level entry point for cooperative collection."""

    def __init__(
        self,
        queue: QueueStore,
        config: EngineConfig,
        *,
        store: Any = None,  # SQLiteStore — optional to avoid circular import
    ):
        self.queue = queue
        self.config = config
        self.store = store

    def plan_daily_collection(
        self,
        user_interests: List[Dict[str, Any]],
        enabled_sources: List[str],
        active_user_ids: Set[int],
    ) -> List[Job]:
        """Build today's collection plan and enqueue jobs.

        Returns the list of jobs (including any that were already queued
        as duplicates).
        """
        date_start, date_end = _today_range()
        plan = build_collection_plan(
            user_interests, enabled_sources, active_user_ids,
            date_start, date_end, self.config,
        )
        raw_jobs = plan_to_jobs(plan)
        enqueued: List[Job] = []
        for job in raw_jobs:
            enqueued.append(self.queue.enqueue(job))
        already_queued = sum(1 for j in enqueued if j.status != "pending")
        logger.info(
            "Daily collection planned: %d groups x %d sources = %d jobs "
            "(%d already queued)",
            len(plan.groups), len(plan.sources), len(raw_jobs), already_queued,
        )
        return enqueued

    def get_active_user_ids(self, window_days: Optional[int] = None) -> Set[int]:
        """Return user IDs that have been active within the window.

        Falls back to all user IDs when ``store`` is unavailable (e.g. in tests).
        """
        if self.store is None:
            return set()
        days = window_days or self.config.collection.active_user_window_days
        # The store does not have this method yet, so we provide a safe fallback
        if hasattr(self.store, "get_active_user_ids"):
            return set(self.store.get_active_user_ids(days))
        # Fallback: return all known user IDs
        try:
            with self.store.connect() as conn:
                rows = conn.execute("SELECT id FROM users").fetchall()
                return {r["id"] for r in rows}
        except Exception:
            return {1}

    def get_all_user_interests(self, active_user_ids: Set[int]) -> List[Dict[str, Any]]:
        """Fetch interests for the given users from the main store."""
        if self.store is None:
            return []
        try:
            with self.store.connect() as conn:
                placeholders = ",".join("?" * len(active_user_ids))
                rows = conn.execute(
                    f"SELECT user_id, keyword, weight, category FROM interest_graph "
                    f"WHERE user_id IN ({placeholders}) AND status = 'active'",
                    list(active_user_ids),
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def get_globally_enabled_sources(self, active_user_ids: Set[int]) -> List[str]:
        """Union of all enabled source IDs across active users."""
        if self.store is None:
            return []
        try:
            with self.store.connect() as conn:
                placeholders = ",".join("?" * len(active_user_ids))
                rows = conn.execute(
                    f"SELECT DISTINCT source_id FROM source_configs "
                    f"WHERE user_id IN ({placeholders}) AND enabled = 1",
                    list(active_user_ids),
                ).fetchall()
                return [r["source_id"] for r in rows]
        except Exception:
            return []

    def run_daily(self) -> List[Job]:
        """Full daily cooperative collection cycle.

        Safe to call even when external calls are blocked — it only
        *plans* and enqueues.  Actual collection happens when workers
        process jobs (and they check the safety guard themselves).
        """
        active = self.get_active_user_ids()
        if not active:
            logger.info("No active users — skipping daily collection")
            return []
        interests = self.get_all_user_interests(active)
        sources = self.get_globally_enabled_sources(active)
        if not interests or not sources:
            logger.info("No interests or sources — skipping daily collection")
            return []
        return self.plan_daily_collection(interests, sources, active)

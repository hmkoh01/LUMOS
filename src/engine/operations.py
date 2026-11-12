"""Operational wiring for the Engine v2 collection and briefing pipeline.

The engine modules deliberately do not start background work on import.  This
module is the single opt-in runtime used by both Railway and the explicit local
real-service command.  Its SQLite queue is shared by every process using the
same database path; durable dedupe keys therefore protect schedule recovery and
multiple workers alike.
"""

from __future__ import annotations

import os
import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set
from zoneinfo import ZoneInfo

from src.engine.bootstrap import engine_cache_path, initialize_engine
from src.engine.budget.tracker import BudgetTracker
from src.engine.collection.planner import make_dedupe_key
from src.engine.config import EngineConfig
from src.engine.llm.handlers import make_generate_briefing_job
from src.engine.models import Job, JobType
from src.engine.models import RawCandidate, ScoredCandidate
from src.engine.llm.metadata_cards import build_metadata_cards, metadata_publish_allowed
from src.engine.llm.publisher import publish_metadata_pilot_cards
from src.engine.queue.sqlite_store import SQLiteQueueStore
from src.engine.queue.worker import JobDeferred, WorkerPool, register_handler
from src.engine.safety import check_external_call_allowed
from src.sources.collector_registry import CollectorRegistry
from src.sources.collectors.base import SourceQuery
from src.sources.collectors.opendart import OpenDARTCollector
from src.sources.opendart_corporations import QueueCorporationCodeCache
from src.sources.query_planner import QueryPlanner
from src.sources.source_registry import source_availability
from src.context.interest_matching import interest_terms
from src.engine.collection.source_support import collection_support
from src.sources.router import SourceRouter
from src.sources.source_discovery import SourceDiscoveryBacklog, configured_discovery_provider

try:
    KST = ZoneInfo("Asia/Seoul")
except Exception:  # Windows portable builds may not bundle the IANA database.
    # Korea has no DST; retain the explicit zone name while preserving the
    # correct UTC+09:00 schedule semantics without adding a tzdata dependency.
    KST = timezone(timedelta(hours=9), name="Asia/Seoul")


def queue_path() -> Path:
    configured = os.environ.get("LUMOS_ENGINE_QUEUE_DB_PATH", "").strip()
    if configured:
        return Path(configured)
    return engine_cache_path().with_name("engine_queue.sqlite")


def _prepare_briefings_key(user_id: int, cycle: str, interests: Iterable[Dict[str, Any]]) -> str:
    """Return one stable finalizer key per user/cycle/interest snapshot.

    The source collection key remains shared.  Only the per-user dependency
    barrier receives a new key when onboarding or an interest edit changes the
    profile after an earlier finalizer for the same schedule cycle completed.
    """
    snapshot = sorted(
        " ".join(str(row.get("keyword") or "").casefold().split())
        for row in interests if int(row.get("user_id") or -1) == int(user_id)
    )
    digest = hashlib.sha256("\x1f".join(snapshot).encode("utf-8")).hexdigest()[:12]
    return f"prepare-briefings:{user_id}:{cycle}:{digest}"


def _generate_briefing_key(user_id: int, period: str, cycle: str, profile: Dict[str, Any],
                           interests: Iterable[Dict[str, Any]], sources: Iterable[str]) -> str:
    """Keep one generation per user/period/cycle/**effective** preference snapshot."""
    raw = profile.get("raw_onboarding_json") if isinstance(profile, dict) else {}
    payload = {
        "interests": sorted(" ".join(str(row.get("keyword") or "").casefold().split()) for row in interests),
        "information_types": (raw or {}).get("interest_type_preferences", {}) if isinstance(raw, dict) else {},
        "sources": sorted(str(source) for source in sources),
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"briefing:{user_id}:{period}:{cycle}:{digest}"


class EngineOperations:
    """Coordinates collection, generation, monitoring and KST schedule slots."""

    def __init__(self, store: Any, config: Optional[EngineConfig] = None):
        self.store = store
        self.config = config or EngineConfig.from_env()
        self.queue = SQLiteQueueStore(queue_path())
        self.budget = BudgetTracker(self.config.budget, queue_path())
        self.pool = WorkerPool(self.queue, self.config, worker_id_prefix="lumos-engine")
        self._stop = threading.Event()
        self._scheduler: Optional[threading.Thread] = None
        self._register_handlers()

    def _register_handlers(self) -> None:
        # initialize_engine installs the structured Gemini/Fake provider job
        # handler.  It is still inert unless this runtime's workers are started.
        initialize_engine(self.store, self.config)
        register_handler(JobType.COLLECT, self._collect_handler)
        register_handler(JobType.PREPARE_BRIEFINGS, self._prepare_briefings_handler)
        register_handler(JobType.SOURCE_DISCOVERY, self._source_discovery_handler)

    def start(self) -> None:
        if not self.config.enabled:
            return
        self.pool.start()
        if self.config.collection.scheduler_enabled and self._scheduler is None:
            self._stop.clear()
            self._scheduler = threading.Thread(target=self._schedule_loop, daemon=True, name="lumos-kst-scheduler")
            self._scheduler.start()

    def stop(self) -> None:
        self._stop.set()
        if self._scheduler is not None:
            self._scheduler.join(timeout=5)
            self._scheduler = None
        self.pool.stop()

    def _schedule_loop(self) -> None:
        # A startup pass covers missed slots after PC/server downtime.  Each
        # individual collection job uses a durable once-key, so this is safe.
        while not self._stop.is_set():
            self.run_due_slots()
            self._stop.wait(30)

    def run_due_slots(self, now: Optional[datetime] = None) -> int:
        now = (now or datetime.now(KST)).astimezone(KST)
        due = []
        for slot in self.config.collection.schedule_slots_kst:
            try:
                hour, minute = (int(part) for part in slot.split(":", 1))
            except ValueError:
                continue
            if (now.hour, now.minute) >= (hour, minute):
                due.append((hour, minute))
        # A machine that missed multiple slots performs one catch-up for the
        # latest completed window, not every historical window in sequence.
        if not due:
            return 0
        hour, minute = max(due)
        return self.plan_cycle(f"{now.date().isoformat()}-{hour:02d}{minute:02d}")

    def plan_cycle(self, cycle: str, user_ids: Optional[Set[int]] = None) -> int:
        if not self.config.enabled:
            return 0
        users = user_ids or set(self.store.get_active_user_ids(self.config.collection.active_user_window_days))
        if not users:
            return 0
        interests = self._interests_for_users(users)
        sources = self._enabled_pilot_sources(users)
        if self.config.collection.source_discovery_enabled and interests:
            self._record_source_discovery_gaps(interests, sources)
        if not interests or not sources:
            return 0
        # A terminal prepare job means this user/cycle has already crossed the
        # collection barrier.  Do not let a process restart or a code deploy
        # append brand-new source calls to that finished snapshot: those calls
        # could not feed its already-completed generation jobs.  A genuinely
        # missed slot has no finalizer yet and therefore retains normal
        # catch-up behaviour; a newly onboarded user also has a distinct key.
        settled_cycle_users: Set[int] = set()
        for candidate_user_id in users:
            user_interests = [row for row in interests if int(row["user_id"]) == int(candidate_user_id)]
            existing_finalizer = self.queue.get_job_by_dedupe_key(
                _prepare_briefings_key(candidate_user_id, cycle, user_interests)
            )
            if existing_finalizer and existing_finalizer.status in {"completed", "failed", "cancelled"}:
                settled_cycle_users.add(int(candidate_user_id))
        date_key = cycle[:10]
        created = 0
        grouped: Dict[str, Set[int]] = {}
        shared_source_users: Dict[str, Set[int]] = {}
        shared_source_keywords: Dict[str, Set[str]] = {}
        for row in interests:
            keyword = str(row["keyword"])
            grouped.setdefault(keyword.casefold(), set()).add(int(row["user_id"]))
        for canonical, matching_user_set in grouped.items():
            keyword = next(row["keyword"] for row in interests if str(row["keyword"]).casefold() == canonical)
            matching_users = sorted(matching_user_set)
            # Information-type choices are stored on each user's profile.
            # Do not pool configs and then route with an empty profile: that
            # would silently broaden an "internship" or "AI industry news"
            # request when two people share the same keyword.
            users_by_source: Dict[str, Set[int]] = {}
            verified_opendart_users: Dict[int, str] = {}
            normalized_keyword = " ".join(str(keyword).casefold().split())
            for candidate_user_id in matching_users:
                if candidate_user_id in settled_cycle_users:
                    continue
                user_source_configs = self.store.get_enabled_source_configs(user_id=candidate_user_id)
                profile = self.store.get_profile(user_id=candidate_user_id) or {}
                support = collection_support(
                    keyword, sources, user_source_configs, profile=profile,
                )
                for supported_source in support.get("sources", []):
                    users_by_source.setdefault(str(supported_source), set()).add(candidate_user_id)
                for config_row in user_source_configs:
                    if config_row.get("source_id") != "opendart":
                        continue
                    config_json = dict(config_row.get("config_json") or {})
                    for identity in config_json.get("verified_company_identities") or []:
                        if not isinstance(identity, dict):
                            continue
                        if normalized_keyword != " ".join(str(identity.get("interest") or "").casefold().split()):
                            continue
                        stock_code = str(identity.get("stock_code") or "").strip()
                        if stock_code.isdigit():
                            verified_opendart_users[candidate_user_id] = stock_code
            # A verified company identity is the only non-category route into
            # OpenDART. It never turns a generic economy/industry keyword into
            # a company lookup.
            if verified_opendart_users and "opendart" in sources:
                users_by_source.setdefault("opendart", set()).update(verified_opendart_users)
            for source in sorted(users_by_source):
                job_users = sorted(users_by_source[source])
                verified_stock_code = ""
                if source == "opendart":
                    job_users = sorted(verified_opendart_users)
                    distinct_codes = set(verified_opendart_users.values())
                    if len(job_users) != 1 or len(distinct_codes) != 1:
                        continue
                    verified_stock_code = next(iter(distinct_codes))
                # Festival discovery has no topical query.  One bounded source
                # snapshot is matched to multiple user interests after
                # collection; never call it once per user/interest.
                if source == "tourapi":
                    shared_source_users.setdefault(source, set()).update(job_users)
                    shared_source_keywords.setdefault(source, set()).add(keyword)
                    continue
                key = f"collect:{cycle}:{make_dedupe_key(keyword, source, date_key, date_key)}"
                job = Job(
                    job_type=JobType.COLLECT, dedupe_key=key, priority=90,
                    payload_json={"interest": keyword, "source": source, "user_ids": job_users,
                                  "cycle": cycle, "date_start": date_key, "date_end": date_key,
                                  **({"verified_stock_code": verified_stock_code} if verified_stock_code else {})},
                    max_retries=0 if source == "opendart" else self.config.collection.max_source_retries,
                )
                before = self.queue.find_duplicate(key)
                outcome = self.queue.enqueue_once(job)
                if before is None and outcome.id == job.id:
                    created += 1
        for source, shared_users in shared_source_users.items():
            key = f"collect:{cycle}:{make_dedupe_key('__shared_snapshot__', source, date_key, date_key)}"
            job = Job(
                job_type=JobType.COLLECT, dedupe_key=key, priority=90,
                payload_json={"interest": "", "raw_keywords": sorted(shared_source_keywords[source]),
                              "source": source, "user_ids": sorted(shared_users), "cycle": cycle,
                              "date_start": date_key, "date_end": date_key, "shared_snapshot": True},
                max_retries=0,
            )
            before = self.queue.find_duplicate(key)
            outcome = self.queue.enqueue_once(job)
            if before is None and outcome.id == job.id:
                created += 1
        # A separate durable dependency job is the barrier between cooperative
        # collection and per-user generation.  It is intentionally created
        # even if this cycle's shared collection has already completed: a new
        # user can then reuse those stored source items without recollecting.
        for user_id in users:
            finalizer = Job(
                job_type=JobType.PREPARE_BRIEFINGS,
                dedupe_key=_prepare_briefings_key(user_id, cycle, interests), priority=10,
                payload_json={"user_id": user_id, "cycle": cycle}, max_retries=0,
            )
            self.queue.enqueue_once(finalizer)
        return created

    def _record_source_discovery_gaps(self, interests: Iterable[Dict[str, Any]], sources: Iterable[str]) -> None:
        """Aggregate unsupported categories without retaining user identities."""
        users_by_category: Dict[str, Set[int]] = {}
        for row in interests:
            user_id, keyword = int(row["user_id"]), str(row.get("keyword") or "")
            profile = self.store.get_profile(user_id=user_id) or {}
            configs = self.store.get_enabled_source_configs(user_id=user_id)
            support = collection_support(keyword, sources, configs, profile=profile)
            if support.get("status") == "supported":
                continue
            for category in SourceRouter().classify_interests(profile, [{"keyword": keyword, "status": "active"}]):
                users_by_category.setdefault(category, set()).add(user_id)
        counts = {category: len(user_ids) for category, user_ids in users_by_category.items()}
        if counts:
            backlog = SourceDiscoveryBacklog(
                self.queue,
                window_days=self.config.collection.source_discovery_window_days,
                max_requests_per_day=self.config.collection.source_discovery_max_requests_per_day,
            )
            now = datetime.now(timezone.utc)
            window = backlog.window_key(now, backlog.window_days)
            tokens = {
                category: [backlog.subject_digest(category, window, user_id) for user_id in user_ids]
                for category, user_ids in users_by_category.items()
            }
            backlog.record_missing_categories(counts, observed_at=now, subject_tokens_by_category=tokens)

    def _source_discovery_handler(self, payload: Dict[str, Any], _config: EngineConfig) -> Dict[str, Any]:
        return SourceDiscoveryBacklog(
            self.queue,
            provider=configured_discovery_provider(
                official_directory_enabled=self.config.collection.source_discovery_official_directory_enabled,
            ),
            window_days=self.config.collection.source_discovery_window_days,
            max_requests_per_day=self.config.collection.source_discovery_max_requests_per_day,
        ).execute_discovery(payload)

    def request_user_backfill(self, user_id: int, reason: str = "new_interest") -> int:
        """Queue only the user's new-interest work; no request performs I/O."""
        now = datetime.now(KST)
        due = []
        for slot in self.config.collection.schedule_slots_kst:
            hour, minute = (int(part) for part in slot.split(":", 1))
            if (now.hour, now.minute) >= (hour, minute):
                due.append((hour, minute))
        # Reuse today's completed schedule window when possible.  This makes
        # onboarding and a missed-slot catch-up one shared collection pass.
        suffix = f"{max(due)[0]:02d}{max(due)[1]:02d}" if due else f"bootstrap-{reason}"
        cycle = f"{now.date().isoformat()}-{suffix}"
        return self.plan_cycle(cycle, {user_id})

    def _interests_for_users(self, user_ids: Set[int]) -> List[Dict[str, Any]]:
        if not user_ids:
            return []
        with self.store.connect() as conn:
            placeholders = ",".join("?" for _ in user_ids)
            rows = conn.execute(
                f"SELECT user_id, keyword, weight, category FROM interest_graph "
                f"WHERE status = 'active' AND user_id IN ({placeholders})",
                list(user_ids),
            ).fetchall()
            return [dict(row) for row in rows]

    def _enabled_pilot_sources(self, user_ids: Iterable[int]) -> List[str]:
        allowed = set(self.config.collection.pilot_sources)
        selected: Set[str] = set()
        for user_id in user_ids:
            for row in self.store.get_enabled_source_configs(user_id=user_id):
                if row.get("source_id") == "opendart":
                    # Explicitly named, small Pilot cohort only. An empty
                    # allowlist is fail-closed for this domestic source.
                    if user_id not in set(self.config.collection.opendart_pilot_user_ids):
                        continue
                if row.get("source_id") in allowed and source_availability(
                    row["source_id"], row.get("config_json")
                )["available"]:
                    selected.add(row["source_id"])
        return sorted(selected)

    def _collect_handler(self, payload: Dict[str, Any], config: EngineConfig) -> Dict[str, Any]:
        if not self.budget.can_start_external_job():
            raise RuntimeError("collection budget limit reached")
        check_external_call_allowed(config, call_description="Engine v2 source collection")
        source = str(payload["source"])
        if source not in set(config.collection.pilot_sources):
            raise RuntimeError(f"source {source!r} is outside the approved pilot allowlist")
        raw_interest = str(payload["interest"])
        # English-only pilot APIs (notably HN search) cannot return evidence
        # for a Korean literal.  Use the existing deterministic interest alias
        # terms for the request while retaining the original user interest for
        # all ranking and explanation steps.
        aliases = [term for term in interest_terms(raw_interest) if term and term.isascii()]
        collection_query = max(aliases, key=len) if aliases else raw_interest
        query_params = {"search": True, "raw_interest": raw_interest}
        if source in {"tourapi", "opendart"}:
            request_day = datetime.now(timezone.utc).date().isoformat()
            per_source_limit = (
                config.collection.tourapi_max_requests_per_day
                if source == "tourapi" else config.collection.opendart_max_requests_per_day
            )
            if per_source_limit <= 0:
                raise RuntimeError(f"{source}_request_budget_not_configured")
            if not self.queue.reserve_source_request(source, request_day, per_source_limit):
                raise RuntimeError(f"{source}_daily_request_budget_exhausted")
        if source == "tourapi":
            collection_query = ""
            query_params = {"event_start_date": datetime.now(KST).strftime("%Y%m%d"), "shared_snapshot": True}
        if source == "opendart":
            # OpenDART stays company-tracking only. A broad economic or
            # industry term cannot become an implicit company query.
            collection_query = raw_interest
            query_params = {
                "raw_interest": raw_interest, "company_name": raw_interest,
                "bgn_de": (datetime.now(KST) - timedelta(days=1)).strftime("%Y%m%d"),
                "end_de": datetime.now(KST).strftime("%Y%m%d"), "page_count": 10,
                **({"verified_stock_code": str(payload["verified_stock_code"])} if payload.get("verified_stock_code") else {}),
            }
        if source == "msit_announcements" and payload.get("shared_snapshot"):
            query_params = {
                "raw_interests": list(payload.get("raw_keywords") or []),
                "max_pages": 3, "page_size": 20, "shared_snapshot": True,
            }
        if source == "crossref":
            # The durable Engine path also uses the planner's research search
            # profile.  Without this branch a scheduled collection bypassed
            # the title-scoped query assembled for the Signals pipeline.
            crossref_query = QueryPlanner()._crossref_query(raw_interest, {})
            collection_query = crossref_query["query"]
            query_params = crossref_query["params"]
        if source == "openalex":
            # OpenAlex resets its provider budget at UTC midnight. Reserve one
            # slot per actual period query in the shared SQLite queue before
            # the call, so workers cannot use KST rollover to exceed it.
            request_day = datetime.now(timezone.utc).date().isoformat()
            openalex_queries = [
                SourceQuery(source=source, query=entry["query"], params=entry["params"])
                for entry in QueryPlanner().build_queries(
                    [{"source": "openalex", "category": "RESEARCH", "source_config": {}}],
                    {}, [{"keyword": raw_interest, "status": "active"}],
                )[0]["queries"]
            ]
            # QueryPlanner supplies exactly one monthly shared pool. Daily,
            # weekly, and monthly feeds later evaluate this same source data
            # by real publication date.
            all_items, warnings = [], []
            for query in openalex_queries:
                if not self.queue.reserve_source_request("openalex", request_day, config.collection.openalex_max_requests_per_day):
                    warnings.append("openalex_free_request_budget_exhausted")
                    break
                result = CollectorRegistry().collect(
                    source, [query], limit=min(config.collection.max_items_per_source, 20), mode="live"
                )
                if result.errors:
                    raise RuntimeError("; ".join(result.errors))
                all_items.extend(result.items)
                warnings.extend(result.warnings)
            # DOI/OpenAlex-id based collector ids make this deterministic even
            # if the same work intersects two period windows.
            seen_ids = set()
            result_items = [item for item in all_items if not (item.source_item_id in seen_ids or seen_ids.add(item.source_item_id))]
            result_warnings = warnings
        else:
            query = SourceQuery(source=source, query=collection_query, params=query_params)
            if source == "opendart":
                # The directory is read from the durable queue database, not
                # a per-Worker in-memory map. A stale/missing directory makes
                # the Collector return a safe no-request warning.
                directory = QueueCorporationCodeCache(
                    self.queue,
                    max_age_seconds=config.collection.opendart_corporation_cache_max_age_hours * 3600,
                )
                result = OpenDARTCollector(corporation_cache=directory).collect(
                    [query], limit=min(config.collection.max_items_per_source, 10),
                )
            else:
                result = CollectorRegistry().collect(source, [query], limit=min(config.collection.max_items_per_source, 10), mode="live")
            if result.errors:
                raise RuntimeError("; ".join(result.errors))
            result_items, result_warnings = result.items, result.warnings
        persisted = []
        for item in [item.to_dict() for item in result_items]:
            item_id = self.store.upsert_source_item(item)
            saved = self.store.get_source_item(item_id)
            if saved:
                persisted.append(saved)
        if source == "opendart" and payload.get("verified_stock_code") and len(payload.get("user_ids") or []) == 1:
            # Preserve a non-content outcome so a legitimate empty disclosure
            # search does not regress to "collection pending" after restart.
            user_id = int(payload["user_ids"][0])
            identity = f"{user_id}|{raw_interest}|{payload['verified_stock_code']}"
            observation_key = "opendart-pilot:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            outcome = "candidates_available" if persisted else "normal_empty"
            self.queue.record_source_collection_observation(
                observation_key, "opendart", outcome, candidate_count=len(persisted),
                request_count=1, provider_code="013" if "opendart_no_data" in result_warnings else "",
            )
            # Publish the Pilot source independently and append-only. It must
            # not enter the generic briefing job, which reconciles a whole
            # period and could replace unrelated cards.
            if persisted:
                source_config = self.store.get_source_config("opendart", user_id=user_id)
                config_json = dict((source_config or {}).get("config_json") or {})
                if metadata_publish_allowed("opendart", config_json, user_id=user_id):
                    candidates = [ScoredCandidate(candidate=RawCandidate(
                        source_item_id=item.get("id"), dedupe_key=item.get("dedupe_key", ""), source="opendart",
                        url=item.get("url", ""), title=item.get("title", ""), summary=item.get("summary", ""),
                        author=item.get("author", ""), published_at=item.get("published_at"),
                        metrics=item.get("metrics_json", {}), collected_at=item.get("collected_at"),
                    ), period="daily", importance_score=1.0) for item in persisted]
                    aliases = {raw_interest: candidates[0].candidate.author} if candidates else {}
                    cards, _ = build_metadata_cards(candidates, [raw_interest], set(), set(), display_limit=5,
                                                    verified_company_aliases=aliases)
                    if cards:
                        run_id = self.store.create_pipeline_run("engine_v2_opendart_pilot", triggered_by="scheduler",
                            interest_snapshot=[{"keyword": raw_interest, "status": "active"}],
                            selected_sources=["opendart"], user_id=user_id)
                        outcome = publish_metadata_pilot_cards(self.store, cards, user_id=user_id, pipeline_run_id=run_id)
                        self.store.complete_pipeline_run(run_id, {**outcome, "period": "daily",
                            "candidate_count": len(candidates), "metadata_published_candidate_count": len(cards),
                            "selected_sources": ["opendart"], "llm_call_count": 0, "translation_call_count": 0}, user_id=user_id)
        self.budget.record(__import__("src.engine.models", fromlist=["UsageRecord"]).UsageRecord(
            event_type="collection", metadata={"source": source, "item_count": len(persisted)}
        ))
        return {"source": source, "item_count": len(persisted), "warnings": result_warnings}

    def _prepare_briefings_handler(self, payload: Dict[str, Any], _config: EngineConfig) -> Dict[str, Any]:
        """Generate only after every collection dependency in this cycle settles.

        This is a real dependency barrier, not a blind timeout: it queries the
        durable queue state for this user/cycle and defers itself only while a
        matching collection job is pending or running.  Failed collection jobs
        are terminal so a useful partial result (or an honest shortage state)
        can still be published.
        """
        user_id = int(payload["user_id"])
        cycle = str(payload["cycle"])
        unfinished = []
        for job in self.queue.list_jobs(job_type=JobType.COLLECT, limit=1000):
            job_users = {int(value) for value in job.payload_json.get("user_ids", [])}
            if str(job.payload_json.get("cycle", "")) == cycle and user_id in job_users and job.status in {"pending", "running"}:
                unfinished.append(job.id)
        if unfinished:
            raise JobDeferred(1.0, "waiting_for_collection_dependencies")
        self._enqueue_user_periods(user_id, cycle)
        return {"user_id": user_id, "cycle": cycle, "dependencies_complete": True}

    def _enqueue_user_periods(self, user_id: int, cycle: str) -> None:
        profile = self.store.get_profile(user_id=user_id) or {}
        interest_rows = self.store.get_interests(limit=50, user_id=user_id)
        interests = [row["keyword"] for row in interest_rows if row.get("status") == "active"]
        if not interests:
            return
        enabled_source_configs = self.store.get_enabled_source_configs(user_id=user_id)
        supported_sources: Set[str] = set()
        for keyword in interests:
            support = collection_support(
                keyword, self.config.collection.pilot_sources, enabled_source_configs, profile=profile,
            )
            supported_sources.update(str(source) for source in support.get("sources", []))
        sources = {row["source_id"] for row in enabled_source_configs if row["source_id"] in supported_sources}
        # The one-user OpenDART Pilot publishes through its own append-only,
        # metadata-only path in ``_collect_handler``.  It must not also make
        # an otherwise empty generic LLM briefing appear runnable: that used
        # to create three candidate-free daily/weekly/monthly runs after a
        # normal empty disclosure observation.
        opendart_config = next((dict(row.get("config_json") or {}) for row in enabled_source_configs
                                if row.get("source_id") == "opendart"), {})
        generic_sources = {
            source for source in sources
            if not (source == "opendart" and opendart_config.get("pilot_mode") == "single_user_metadata_only")
        }
        # There is no meaningful generic LLM generation for a user with no
        # operational source on that path. Keep the first-briefing state
        # honest instead of recording an empty pipeline run.
        if not generic_sources:
            return
        since = (datetime.now(KST) - timedelta(days=31)).date().isoformat()
        candidates = []
        for item in self.store.get_source_items_since(since):
            if item.get("source") not in generic_sources:
                continue
            candidates.append({"source_item_id": item.get("id"), "dedupe_key": item.get("dedupe_key", ""),
                               "source": item.get("source", ""), "url": item.get("url", ""),
                               "title": item.get("title", ""), "summary": item.get("summary", ""),
                               "author": item.get("author", ""), "published_at": item.get("published_at"),
                               "metrics": item.get("metrics_json", {}), "collected_at": item.get("collected_at")})
        requested_limit = int(self.store.get_settings(user_id=user_id).get("signal_count", 3))
        display_limit = min(max(1, requested_limit), self.config.budget.max_briefing_display_count)
        # Generate a small display set plus reserves.  The publisher can
        # backfill from those reserves without another external LLM call.
        generation_limit = min(len(candidates), int(display_limit) + 3)
        for period in ("daily", "weekly", "monthly"):
            key = _generate_briefing_key(user_id, period, cycle, profile, interest_rows, generic_sources)
            # A completed calendar job is a valid prior result, not a reason
            # to create another running pipeline row. This check is only an
            # optimisation; enqueue_once below still closes a worker race.
            if self.queue.get_job_by_dedupe_key(key) is not None:
                continue
            run_id = self.store.create_pipeline_run("engine_v2", triggered_by="scheduler", profile_snapshot=profile,
                                                    interest_snapshot=interest_rows,
                                                    selected_sources=sorted(generic_sources), user_id=user_id)
            payload = {"user_id": user_id, "pipeline_run_id": run_id, "period": period,
                       "role": profile.get("role", ""), "interests": interests,
                       # A negative rating is a user-level exclusion for the
                       # same source item, not merely a dismissal from one
                       # calendar tab.  This prevents the exact article from
                       # returning in the weekly/monthly briefing.
                       "ignored_keys": self.store.get_engine_preference_keys(
                           period, "ignored", user_id=user_id, across_periods=True,
                       ),
                       "tracked_keys": self.store.get_engine_preference_keys(period, "tracked", user_id=user_id),
                       "display_limit": display_limit, "generation_limit": generation_limit,
                       "candidates": candidates}
            new_job = make_generate_briefing_job(dedupe_key=key, payload=payload, priority=20)
            queued = self.queue.enqueue_once(new_job)
            if queued is not new_job:
                # Another worker won the race. This run never generated a
                # briefing, so persist an explicit skipped relation instead
                # of leaving it as a misleading running run.
                self.store.skip_pipeline_run(run_id, {
                    "period": period,
                    "generation_state": "skipped_deduplicated",
                    "deduplicated_to_job_id": queued.id,
                    "deduplicated_to_pipeline_run_id": queued.payload_json.get("pipeline_run_id"),
                    "candidate_count": len(candidates),
                    "selected_sources": sorted(generic_sources),
                }, user_id=user_id)

    def status(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        now = datetime.now(KST)
        slots = []
        for value in self.config.collection.schedule_slots_kst:
            hour, minute = (int(part) for part in value.split(":", 1))
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            slots.append(target)
        jobs = self.queue.list_jobs(limit=100)
        relevant = [job for job in jobs if user_id is None or
                    int(job.payload_json.get("user_id", -1)) == user_id or
                    user_id in {int(value) for value in job.payload_json.get("user_ids", [])}]
        latest = relevant[0] if relevant else None
        active_collection = any(job.job_type == JobType.COLLECT and job.status in {"pending", "running"} for job in relevant)
        active_generation = any(job.job_type in {JobType.PREPARE_BRIEFINGS, JobType.GENERATE_BRIEFING}
                                and job.status in {"pending", "running"} for job in relevant)
        periods: Dict[str, Dict[str, Any]] = {}
        if user_id is not None:
            for run in self.store.get_recent_pipeline_runs(limit=100, user_id=user_id):
                summary = run.get("summary_json") or {}
                period = summary.get("period")
                if period and period not in periods:
                    periods[period] = {
                        "run_status": run.get("status"),
                        "candidate_count": int(summary.get("candidate_count", 0)),
                        "date_eligible_count": summary.get("date_eligible_count"),
                        "importance_eligible_count": summary.get("importance_eligible_count"),
                        "card_count": int(summary.get("card_count", 0)),
                    }
        from src.engine.llm.structured_cache import StructuredBriefingCache
        cache = StructuredBriefingCache(engine_cache_path())
        try:
            llm_metrics = cache.metric_summary()
        finally:
            cache.close()
        return {"enabled": self.config.enabled, "scheduler_enabled": self.config.collection.scheduler_enabled,
                "external_calls_allowed": self.config.external_calls_allowed,
                "pilot_sources": list(self.config.collection.pilot_sources),
                "next_collection_at_kst": min(slots).isoformat() if slots else None,
                "queue": self.queue.monitoring_summary(), "usage": self.budget.get_usage_summary(),
                "llm_metrics": llm_metrics, "periods": periods,
                "active_collection": active_collection, "active_generation": active_generation,
                "latest_job": latest.to_dict() if latest else None}


_runtime: Optional[EngineOperations] = None


def start_engine_operations(store: Any, config: Optional[EngineConfig] = None) -> Optional[EngineOperations]:
    global _runtime
    cfg = config or EngineConfig.from_env()
    if not cfg.enabled:
        return None
    if _runtime is None:
        _runtime = EngineOperations(store, cfg)
        _runtime.start()
    return _runtime


def get_engine_operations() -> Optional[EngineOperations]:
    return _runtime


def stop_engine_operations() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.stop()
        _runtime = None

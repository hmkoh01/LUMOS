"""Regression tests for first-briefing scheduling and empty-feed status."""

from types import SimpleNamespace

from src.api.signals import _first_briefing_state
from src.engine.config import CollectionConfig, EngineConfig
from src.engine.models import JobType
from src.engine.operations import _prepare_briefings_key
from src.engine.operations import EngineOperations


class _ReadOnlyStore:
    def __init__(self, *, runs=None):
        self._runs = runs or []

    def get_profile(self, *, user_id):
        return {"raw_onboarding_json": {}}

    def get_source_configs(self, *, user_id):
        return []

    def get_interests(self, *, limit, user_id):
        return [{"keyword": "AI industry news", "status": "active"}]

    def get_recent_pipeline_runs(self, *, limit, user_id):
        return self._runs


def test_prepare_finalizer_key_changes_only_when_interest_snapshot_changes():
    before = [{"user_id": 890, "keyword": "AI agent"}]
    same_profile = [{"user_id": 890, "keyword": "  ai   AGENT "}]
    after = before + [{"user_id": 890, "keyword": "internship"}]

    assert _prepare_briefings_key(890, "2026-11-11-0630", before) == _prepare_briefings_key(
        890, "2026-11-11-0630", same_profile
    )
    assert _prepare_briefings_key(890, "2026-11-11-0630", before) != _prepare_briefings_key(
        890, "2026-11-11-0630", after
    )


def test_empty_first_briefing_never_claims_candidates_when_source_is_not_operational(monkeypatch):
    monkeypatch.setattr(
        "src.api.signals.collection_support",
        lambda *_args, **_kwargs: {"status": "awaiting_approved_source"},
    )
    config = SimpleNamespace(collection=SimpleNamespace(pilot_sources=("github", "hackernews")))
    assert _first_briefing_state(_ReadOnlyStore(), 890, config, "daily", 0) == "no_operational_source"


def test_empty_first_briefing_distinguishes_pending_from_completed_zero_candidate_run(monkeypatch):
    monkeypatch.setattr(
        "src.api.signals.collection_support",
        lambda *_args, **_kwargs: {"status": "supported"},
    )
    config = SimpleNamespace(collection=SimpleNamespace(pilot_sources=("github",)))
    assert _first_briefing_state(_ReadOnlyStore(), 890, config, "daily", 0) == "collection_pending"

    completed = [{"status": "completed", "summary_json": {"period": "daily", "card_count": 0}}]
    assert _first_briefing_state(_ReadOnlyStore(runs=completed), 890, config, "daily", 0) == "no_matching_candidates"
    assert _first_briefing_state(_ReadOnlyStore(runs=completed), 890, config, "daily", 1) == "candidates_available"


class _Queue:
    def __init__(self):
        self.jobs = []

    def find_duplicate(self, _key):
        return None

    def enqueue_once(self, job):
        self.jobs.append(job)
        return job


class _PlanningStore:
    def get_enabled_source_configs(self, *, user_id):
        return []

    def get_profile(self, *, user_id):
        return {"raw_onboarding_json": {"interest_type_preferences": {"AI": [
            "ai_industry_news" if user_id == 10 else "ai_open_source"
        ]}}}


def test_shared_keyword_respects_each_users_selected_information_type(monkeypatch):
    operations = object.__new__(EngineOperations)
    operations.store = _PlanningStore()
    operations.queue = _Queue()
    operations.config = EngineConfig(
        enabled=True,
        collection=CollectionConfig(pilot_sources=("official_ai_blogs", "github")),
    )
    operations._interests_for_users = lambda _users: [
        {"user_id": 10, "keyword": "AI", "weight": 1.0, "category": ""},
        {"user_id": 11, "keyword": "AI", "weight": 1.0, "category": ""},
    ]
    operations._enabled_pilot_sources = lambda _users: ["official_ai_blogs", "github"]

    def support(_keyword, _sources, _configs, *, profile=None):
        selected = profile["raw_onboarding_json"]["interest_type_preferences"]["AI"][0]
        return {"status": "supported", "sources": [
            "official_ai_blogs" if selected == "ai_industry_news" else "github"
        ]}

    monkeypatch.setattr("src.engine.operations.collection_support", support)
    operations.plan_cycle("2026-11-11-bootstrap-onboarding", {10, 11})

    jobs = [job for job in operations.queue.jobs if job.job_type == JobType.COLLECT]
    assert {(job.payload_json["source"], tuple(job.payload_json["user_ids"])) for job in jobs} == {
        ("official_ai_blogs", (10,)), ("github", (11,)),
    }

"""Data models for the v2 engine.

Plain dataclasses — no ORM dependency.  Serialisable to/from dicts for
SQLite JSON columns.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    COLLECT = "collect"
    EVALUATE = "evaluate"
    GENERATE_BRIEFING = "generate_briefing"
    BACKFILL = "backfill"
    INTEREST_RESOLVE = "interest_resolve"


class Period(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class LLMTier(str, Enum):
    RULE = "rule"
    CHEAP = "cheap"
    EXPENSIVE = "expensive"


# ---------------------------------------------------------------------------
# Job Queue
# ---------------------------------------------------------------------------

@dataclass
class Job:
    id: Optional[int] = None
    job_type: str = JobType.COLLECT
    dedupe_key: str = ""
    status: str = JobStatus.PENDING
    priority: int = 50
    payload_json: Dict[str, Any] = field(default_factory=dict)
    result_json: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3
    lease_owner: Optional[str] = None
    lease_expires_at: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

@dataclass
class InterestGroup:
    """A normalised cluster of user interests that maps to one collection job."""
    canonical_keyword: str
    raw_keywords: List[str] = field(default_factory=list)
    user_ids: List[int] = field(default_factory=list)
    weight: float = 1.0
    category: Optional[str] = None


@dataclass
class CollectionPlan:
    """What to collect in a single cooperative run."""
    groups: List[InterestGroup] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    date_range_start: str = ""
    date_range_end: str = ""
    budget_remaining_jobs: int = 50


# ---------------------------------------------------------------------------
# Candidates & Evaluation
# ---------------------------------------------------------------------------

@dataclass
class RawCandidate:
    """A source item enriched with collection metadata."""
    source_item_id: Optional[int] = None
    dedupe_key: str = ""
    source: str = ""
    url: str = ""
    title: str = ""
    summary: str = ""
    author: str = ""
    published_at: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    matched_interests: List[str] = field(default_factory=list)
    collected_at: Optional[str] = None


@dataclass
class ScoredCandidate:
    """A candidate with period-specific importance scores."""
    candidate: RawCandidate = field(default_factory=RawCandidate)
    period: str = Period.DAILY
    importance_score: float = 0.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    rank: int = 0


# ---------------------------------------------------------------------------
# LLM & Briefing Cache
# ---------------------------------------------------------------------------

@dataclass
class KoreanBriefing:
    """Shared Korean-language briefing for a source item."""
    dedupe_key: str = ""
    display_title_ko: str = ""
    headline_summary_ko: str = ""
    key_facts_ko: List[str] = field(default_factory=list)
    generated_by: str = LLMTier.RULE
    confidence: float = 1.0
    created_at: Optional[str] = None
    expires_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecommendationReason:
    """Per-user explanation of why a briefing card is recommended."""
    user_id: int = 0
    dedupe_key: str = ""
    reason_ko: str = ""
    matched_interests: List[str] = field(default_factory=list)
    source_features: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Budget / Usage
# ---------------------------------------------------------------------------

@dataclass
class UsageRecord:
    """A single usage event for cost tracking."""
    user_id: int = 0
    event_type: str = ""  # "llm_cheap", "llm_expensive", "collection", "chat"
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None

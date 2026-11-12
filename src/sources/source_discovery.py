"""Fail-closed backlog for official source discovery.

Candidates are operational metadata, not collected editorial content.  The
default provider deliberately performs no web requests; an operator may later
install an independently approved provider that implements ``WebDiscoveryProvider``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import os
from typing import Dict, Iterable, List, Protocol

from src.engine.models import Job, JobType


DISCOVERY_STATUSES = frozenset({
    "discovered", "requires_registration", "permission_review", "adapter_needed",
    "ready_for_canary", "canary_passed", "approved", "enabled", "rejected",
})

# Operational provenance only: neither a query nor a provider result is kept.
DISCOVERY_ORIGINS = frozenset({
    "seed", "official_directory_catalogue", "official_directory_live", "manual",
})

ENTRY_KINDS = frozenset({"source_candidate", "discovery_infrastructure"})


class WebDiscoveryProvider(Protocol):
    """Optional provider for official-document discovery.

    Implementations must return independently verified official URLs only.
    Search snippets and raw results must never be persisted by this subsystem.
    """
    enabled: bool

    def discover_official_sources(self, categories: Iterable[str]) -> List[Dict[str, object]]: ...


class DisabledWebDiscoveryProvider:
    enabled = False

    def discover_official_sources(self, categories: Iterable[str]) -> List[Dict[str, object]]:
        return []


@dataclass
class OfficialDirectoryProvider:
    """Provider for a pre-approved official directory export.

    It deliberately accepts already verified document metadata, not a web
    search response. This makes scheduled discovery useful without retaining
    results/snippets from an unlicensed search provider.
    """
    records: Iterable[Dict[str, object]]
    enabled: bool = True

    def discover_official_sources(self, categories: Iterable[str]) -> List[Dict[str, object]]:
        wanted = set(categories)
        results = []
        for record in self.records:
            if not wanted.intersection(record.get("categories", [])):
                continue
            candidate = dict(record)
            candidate.setdefault("discovery_origin", "official_directory_catalogue")
            results.append(candidate)
        return results


OFFICIAL_SEED_CANDIDATES = (
    {
        "source_id": "employment24", "domain": "work24.go.kr",
        "official_url": "https://www.work24.go.kr/cm/e/a/0110/selectOpenApiIntro.do",
        "documentation_url": "https://www.work24.go.kr/cm/e/a/0110/selectOpenApiIntro.do",
        "registration_url": "https://www.work24.go.kr/cm/e/a/0110/selectOpenApiIntro.do",
        "categories": ["CAREER"], "authentication": "Work24 enterprise-member API key",
        "registration_required": True, "license_review_status": "not_reviewed",
        "capabilities": {"information_types": ["internships", "junior_jobs"], "metadata_only": True},
        "date_coverage": "posting registration date and closing date when supplied",
        "priority": 90, "candidate_status": "requires_registration", "adapter_status": "implemented",
        "next_action": "운영자 기업회원 API 활용신청·이용조건 검토 후 격리 Canary",
    },
    {
        "source_id": "msit_press_rss", "domain": "msit.go.kr",
        "official_url": "https://www.msit.go.kr/user/rss/rss.do?bbsSeqNo=94",
        "documentation_url": "https://www.msit.go.kr/contents/cont.do?mId=173&mPid=147&sCode=user",
        "registration_url": "",
        "categories": ["AI_TREND", "INDUSTRY_POLICY"], "authentication": "none (public RSS)",
        "registration_required": False, "license_review_status": "per_item_license_review_required",
        "capabilities": {"information_types": ["industry_news", "press_release"], "metadata_only": True},
        "date_coverage": "feed publication timestamp; verify official page date before ranking",
        "priority": 85, "candidate_status": "permission_review", "adapter_status": "implemented",
        "next_action": "게시물별 이용허락·공식 발행일 검증 후 메타데이터 Canary",
    },
    {
        "source_id": "openai_news_rss", "domain": "openai.com",
        "official_url": "https://openai.com/news/rss.xml", "documentation_url": "https://openai.com/news/",
        "registration_url": "", "categories": ["AI_TREND"], "authentication": "none (public RSS)",
        "registration_required": False, "license_review_status": "permission_review",
        "capabilities": {"information_types": ["industry_news", "official_update"], "metadata_only": True},
        "date_coverage": "publisher RSS publication timestamp", "priority": 80,
        "candidate_status": "permission_review", "adapter_status": "implemented",
        "next_action": "메타데이터 표시·AI 처리·재제공 권한을 출처별로 확인",
    },
    {
        "source_id": "google_official_blog_rss", "domain": "blog.google",
        "official_url": "https://blog.google/rss/", "documentation_url": "https://blog.google/about/",
        "registration_url": "", "categories": ["AI_TREND"], "authentication": "none (public RSS)",
        "registration_required": False, "license_review_status": "permission_review",
        "capabilities": {"information_types": ["industry_news", "official_update"], "metadata_only": True},
        "date_coverage": "publisher RSS publication timestamp", "priority": 80,
        "candidate_status": "permission_review", "adapter_status": "implemented",
        "next_action": "AI 관련 게시물 필터와 메타데이터 재이용 권한 검토",
    },
    {
        "source_id": "public_institution_jobs", "domain": "data.go.kr",
        "provider_name": "재정경제부",
        "official_url": "https://www.data.go.kr/data/15125273/openapi.do",
        "documentation_url": "https://www.data.go.kr/data/15125273/openapi.do",
        "registration_url": "https://www.data.go.kr/data/15125273/openapi.do",
        "categories": ["CAREER"], "authentication": "data.go.kr service key",
        "registration_required": True, "license_review_status": "permission_review",
        "capabilities": {"information_types": ["internships", "junior_jobs"], "metadata_only": True},
        "date_coverage": "announcement start/end fields; application status requires separate verification",
        "priority": 88, "candidate_status": "permission_review", "adapter_status": "implemented",
        "next_action": "Confirm 15125273 production approval, current codebook, metadata redisplay/AI scope, then run one intern-only metadata Canary",
    },
    {
        "source_id": "msit_announcements", "domain": "data.go.kr",
        "official_url": "https://www.data.go.kr/data/15074634/openapi.do",
        "documentation_url": "https://www.data.go.kr/data/15074634/openapi.do",
        "registration_url": "https://www.data.go.kr/data/15074634/openapi.do",
        "categories": ["INDUSTRY_POLICY", "STARTUP_PROGRAM", "RESEARCH"],
        "authentication": "data.go.kr service key", "registration_required": True,
        "license_review_status": "metadata_scope_confirmed",
        "capabilities": {"information_types": ["government_policy", "government_rnd_announcement"], "metadata_only": True},
        "date_coverage": "official press date", "priority": 70,
        "candidate_status": "ready_for_canary", "adapter_status": "implemented",
        "next_action": "운영계정 범위에서 메타데이터 전용 Canary 후 운영자 승인",
    },
)

# Discovery infrastructure is not a content source and can never be routed to
# readers.  Its registration status must not suppress demand aggregation or
# candidate management for other official sources.
OFFICIAL_DISCOVERY_INFRASTRUCTURE = (
    {
        "source_id": "data_go_kr_catalogue_api", "domain": "data.go.kr",
        "provider_name": "공공데이터활용지원센터",
        "official_url": "https://www.data.go.kr/data/15077093/openapi.do",
        "documentation_url": "https://www.data.go.kr/data/15077093/openapi.do",
        "registration_url": "https://www.data.go.kr/data/15077093/openapi.do",
        "categories": [], "authentication": "data.go.kr service key",
        "registration_required": True, "license_review_status": "permission_review",
        "capabilities": {"discovery_only": True, "metadata_only": True,
                           "live_query_count": 0, "approved_for_automatic_access": False},
        "date_coverage": "catalogue record registration and update dates",
        "priority": 0, "entry_kind": "discovery_infrastructure",
        "candidate_status": "requires_registration", "adapter_status": "not_applicable",
        "next_action": "Confirm 15077093 application approval and automated metadata-use scope before one isolated directory canary",
    },
)

# Independently verified directory metadata.  This is not a scraped search
# result and is deliberately separate from the always-seeded backlog.  It can
# be supplied to ``OfficialDirectoryProvider`` only after an operator approves
# this catalogue as a discovery source.
VERIFIED_OFFICIAL_DIRECTORY_CANDIDATES = (
    {
        "source_id": "public_service_jobs", "domain": "data.go.kr",
        "provider_name": "인사혁신처",
        "official_url": "https://www.data.go.kr/data/15156780/openapi.do",
        "documentation_url": "https://www.data.go.kr/data/15156780/openapi.do",
        "registration_url": "https://www.data.go.kr/data/15156780/openapi.do",
        "categories": ["CAREER"], "authentication": "data.go.kr service key",
        "registration_required": True, "license_review_status": "permission_review",
        "capabilities": {"information_types": ["junior_jobs", "public_jobs"], "metadata_only": True},
        "date_coverage": "official announcement registration date; closing date requires schema verification",
        "priority": 82, "candidate_status": "adapter_needed", "adapter_status": "schema_pending",
        "next_action": "발급 Swagger/모델로 목록 필드 확정 후 API 활용신청·격리 Canary",
    },
)


def verified_official_directory_provider() -> OfficialDirectoryProvider:
    """Return the reviewed static-directory provider; callers opt in explicitly."""
    return OfficialDirectoryProvider(VERIFIED_OFFICIAL_DIRECTORY_CANDIDATES)


def configured_discovery_provider(*, official_directory_enabled: bool) -> WebDiscoveryProvider:
    """Select only an explicitly approved discovery provider.

    General web search intentionally has no default implementation.  The
    reviewed official directory contains no search snippets or response data,
    but it still remains opt-in because running it creates backlog records.
    """
    if official_directory_enabled:
        return verified_official_directory_provider()
    return DisabledWebDiscoveryProvider()


def candidate_can_route(candidate: Dict[str, object]) -> bool:
    """A credential alone never makes a candidate eligible for routing."""
    checks = dict((candidate.get("capabilities") or {}).get("activation_checks") or {})
    return (
        candidate.get("entry_kind", "source_candidate") == "source_candidate"
        and candidate.get("candidate_status") == "enabled"
        and candidate.get("adapter_status") == "implemented"
        and all(checks.get(key) is True for key in ("credentials_verified", "schema_verified", "license_verified", "canary_passed", "operator_approved"))
    )


@dataclass
class SourceDiscoveryBacklog:
    queue: object
    provider: WebDiscoveryProvider = DisabledWebDiscoveryProvider()
    window_days: int = 7
    max_requests_per_day: int = 0

    def seed_official_candidates(self) -> List[Dict[str, object]]:
        sources = [self.queue.upsert_source_discovery_candidate({**candidate, "discovery_origin": "seed"})
                   for candidate in OFFICIAL_SEED_CANDIDATES]
        for infrastructure in OFFICIAL_DISCOVERY_INFRASTRUCTURE:
            self.queue.upsert_source_discovery_candidate({**infrastructure, "discovery_origin": "seed"})
        return sources

    def record_missing_categories(self, category_user_counts: Dict[str, int], *, observed_at: datetime | None = None,
                                  subject_tokens_by_category: Dict[str, Iterable[str]] | None = None) -> List[str]:
        """Aggregate scheduler demand once per category/window, without user data."""
        now = observed_at or datetime.now(timezone.utc)
        window = self.window_key(now, self.window_days)
        candidates = self.seed_official_candidates()
        scheduled: List[str] = []
        for category, count in category_user_counts.items():
            relevant = [item for item in candidates if category in item.get("categories", [])]
            for candidate in relevant:
                tokens = list((subject_tokens_by_category or {}).get(category, []))
                if tokens:
                    inserted = [
                        self.queue.record_source_discovery_subject_demand(candidate["source_id"], category, window, subject_digest=token)
                        for token in sorted(set(tokens))
                    ]
                    if any(inserted):
                        scheduled.append(str(candidate["source_id"]))
                elif self.queue.record_source_discovery_demand(candidate["source_id"], category, window, user_count=count):
                    scheduled.append(str(candidate["source_id"]))
            # No official candidate yet: enqueue at most one disabled-by-default
            # discovery task per category/window. Its handler cannot call out
            # until an approved provider and nonzero budget are configured.
            if not relevant:
                key = f"source-discovery:{category}:{window}"
                self.queue.enqueue_once(Job(job_type=JobType.SOURCE_DISCOVERY, dedupe_key=key, priority=1,
                                            payload_json={"category": category, "window": window}, max_retries=0))
        return scheduled

    @staticmethod
    def window_key(observed_at: datetime, window_days: int = 7) -> str:
        return f"{observed_at.date().isoformat()}-w{observed_at.timetuple().tm_yday // max(1, window_days)}"

    @staticmethod
    def subject_digest(category: str, window: str, user_id: int) -> str:
        """Return a non-reversible, window-scoped dedupe token; never store user_id."""
        secret = os.environ.get("LUMOS_SOURCE_DISCOVERY_DEDUP_SECRET", "lumos-discovery-local-only").encode("utf-8")
        return hmac.new(secret, f"{category}\x1f{window}\x1f{int(user_id)}".encode("utf-8"), hashlib.sha256).hexdigest()

    def execute_discovery(self, payload: Dict[str, object]) -> Dict[str, object]:
        """Run only with an explicitly enabled provider and bounded global budget."""
        if not self.provider.enabled or self.max_requests_per_day <= 0:
            return {"status": "provider_disabled", "stored_candidates": 0}
        day = datetime.now(timezone.utc).date().isoformat()
        if not self.queue.reserve_source_request("source_discovery", day, self.max_requests_per_day):
            return {"status": "budget_exhausted", "stored_candidates": 0}
        records = self.provider.discover_official_sources([str(payload.get("category") or "")])
        stored = [self.queue.upsert_source_discovery_candidate(record) for record in records]
        return {"status": "completed", "stored_candidates": len(stored)}

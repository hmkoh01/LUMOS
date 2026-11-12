"""Bounded, source-shared discovery plans for domestic opportunity APIs.

These plans deliberately contain *only* filters confirmed by the issued API
schemas.  They are planning data, not permission to activate a source or to
make a network request.  In particular, code-valued job filters are omitted
until an operator provides the matching official code definition table.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence


PUBLIC_JOBS_MAX_REQUESTS_PER_CYCLE = 4
MSS_SUPPORT_MAX_REQUESTS_PER_CYCLE = 3
MAX_ROWS_PER_REQUEST = 20


@dataclass(frozen=True)
class DiscoveryPlan:
    source: str
    profile_id: str
    params: Dict[str, str]
    shared_scope: str
    requires_codebook: tuple[str, ...] = ()
    direct_evidence_terms: tuple[str, ...] = ()


# ``recrutPbancTtl`` is a documented free-text condition.  These terms do not
# stand in for NCS/recruitment/hire codes; the code filters remain absent until
# the official table is supplied with its version and effective dates.
PUBLIC_JOB_PROFILES: Dict[str, Dict[str, Any]] = {
    "junior_developer": {
        "title_query": "개발",
        "information_types": ("junior_jobs",),
        "direct_evidence_terms": ("개발", "소프트웨어", "software", "developer", "programming", "coding"),
        "requires_codebook": ("recrutSe", "hireTypeLst", "ncsCdLst"),
    },
    "it_software": {
        "title_query": "소프트웨어",
        "information_types": (),
        "direct_evidence_terms": ("개발", "소프트웨어", "software", "developer", "it"),
        "requires_codebook": ("ncsCdLst",),
    },
    "youth_intern": {
        "title_query": "인턴",
        "information_types": ("internships",),
        "direct_evidence_terms": ("인턴", "intern"),
        "requires_codebook": ("recrutSe", "hireTypeLst"),
    },
    "general_junior": {
        "title_query": "신입",
        "information_types": ("junior_jobs",),
        "direct_evidence_terms": ("신입", "new hire", "entry"),
        "requires_codebook": ("recrutSe", "hireTypeLst"),
    },
}


# Categories are retained for display/audit but cannot by themselves prove a
# match.  Each profile needs direct evidence in title, purpose, target, or
# support type before an item is promoted to personal ranking.
SUPPORT_PROGRAM_PROFILES: Dict[str, tuple[str, ...]] = {
    "technical_startup": ("기술창업", "기술 창업", "딥테크", "deep tech", "기술사업화", "technology startup"),
    "general_startup": ("창업", "스타트업", "startup"),
    "small_business": ("소상공인", "small business"),
    "digital_commerce": ("디지털커머스", "디지털 커머스", "digital commerce", "e-commerce", "ecommerce"),
    "online_market_access": ("온라인 판매", "온라인판로", "온라인 판로", "판로지원", "판로 지원", "market access"),
}

SUPPORT_INFORMATION_TYPE_PROFILES = {
    "startup_support": "general_startup",
    "technology_startup_support": "technical_startup",
    "small_business_support": "small_business",
    "digital_commerce_support": "digital_commerce",
    "online_market_access": "online_market_access",
}


def analyse_public_job_title_coverage(titles: Iterable[str]) -> Dict[str, List[str]]:
    """Classify coverage of the current *deliberately narrow* title plans.

    This is a Fixture/diagnostic aid.  It does not turn uncovered labels into
    new provider queries: terms such as ``전산직`` or ``정보보안`` should be
    connected to official NCS/recruitment definitions before being expanded.
    """
    result = {"developer": [], "software": [], "intern": [], "junior": [], "uncovered_it_role": [], "other": []}
    for original in titles:
        title = str(original)
        value = title.casefold()
        if "개발" in value or "developer" in value:
            result["developer"].append(title)
        elif "소프트웨어" in value or "software" in value:
            result["software"].append(title)
        elif "인턴" in value or "intern" in value:
            result["intern"].append(title)
        elif "신입" in value or "new hire" in value:
            result["junior"].append(title)
        elif any(term in value for term in ("전산", "정보보안", "보안", " it ", "it 기술", "it기술", "sw ", "sw직")) or value.startswith("it "):
            result["uncovered_it_role"].append(title)
        else:
            result["other"].append(title)
    return result


def dedupe_source_items(items: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Merge multi-profile results by official source ID before ranking."""
    seen: set[str] = set()
    unique: List[Mapping[str, Any]] = []
    for item in items:
        identifier = str(item.get("source_item_id") or item.get("recrutPblntSn") or item.get("sprtBizCd") or "").strip()
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        unique.append(item)
    return unique


_DEVELOPER_ROLE = re.compile(
    r"(?:\b(?:software\s+(?:developer|engineer|development)|developer|programmer|programming|coding|"
    r"backend(?:\s+developer)?|frontend(?:\s+developer)?)\b|"
    r"(?:\uc18c\ud504\ud2b8\uc6e8\uc5b4\s*(?:\uac1c\ubc1c|\uc5d4\uc9c0\ub2c8\uc5b4)|\uac1c\ubc1c\uc790|"
    r"\ubc31\uc5d4\ub4dc|\ud504\ub860\ud2b8\uc5d4\ub4dc|\uc6f9\s*\uac1c\ubc1c|\uc571\s*\uac1c\ubc1c|"
    r"it\s*\uac1c\ubc1c|\ud504\ub85c\uadf8\ub798\uba38|\ud504\ub85c\uadf8\ub798\ubc0d)|"
    r"(?:^|[\s\u00b7,/(])sw(?:[\s\u00b7,/)\uc9c1\ubb34]|$))",
    re.IGNORECASE,
)


def has_developer_role_evidence(*fields: Any) -> bool:
    """Reject organisation names containing '개발' unless a role is explicit."""
    return bool(_DEVELOPER_ROLE.search(" ".join(str(value or "") for value in fields)))


def public_job_discovery_plans(
    interests: Iterable[str],
    *,
    information_types: Iterable[str] = (),
    code_filters: Mapping[str, str] | None = None,
    codebook_verified: bool = False,
    page_no: int = 1,
    rows: int = MAX_ROWS_PER_REQUEST,
) -> List[DiscoveryPlan]:
    """Return at most four shared public-jobs requests.

    Only explicit entries from an official codebook may populate code-valued
    filters.  Passing arbitrary values silently would turn user text into
    undocumented provider codes, so unsupported keys are ignored.
    """
    intent = " ".join(str(value).casefold() for value in interests)
    requested_types = {str(value) for value in information_types}
    selected: List[str] = []
    if any(term in intent for term in ("개발", "developer", "software", "소프트웨어")):
        selected.extend(("junior_developer", "it_software"))
    if any(term in intent for term in ("인턴", "intern")) or "internships" in requested_types:
        selected.append("youth_intern")
    if any(term in intent for term in ("신입", "취업", "채용", "new hire")) or "junior_jobs" in requested_types:
        selected.append("general_junior")
    if not selected and ("career" in requested_types or "junior_jobs" in requested_types):
        selected.append("general_junior")

    official_filters = _official_code_filters(code_filters) if codebook_verified else {}
    plans: List[DiscoveryPlan] = []
    for profile_id in _unique(selected)[:PUBLIC_JOBS_MAX_REQUESTS_PER_CYCLE]:
        profile = PUBLIC_JOB_PROFILES[profile_id]
        params = {
            "pageNo": str(max(1, page_no)),
            "numOfRows": str(_bounded_rows(rows)),
            "ongoingYn": "Y",
            "resultType": "json",
            "recrutPbancTtl": profile["title_query"],
            **official_filters,
        }
        plans.append(DiscoveryPlan(
            source="public_institution_jobs", profile_id=profile_id, params=params,
            shared_scope="public_institution_jobs:current-opportunities",
            requires_codebook=tuple(profile["requires_codebook"]),
            direct_evidence_terms=tuple(profile["direct_evidence_terms"]),
        ))
    return plans


def support_program_collection_plan(*, year: int | str, page_no: int = 1, rows: int = MAX_ROWS_PER_REQUEST) -> DiscoveryPlan:
    """Build the only documented MSS support-programme request shape.

    The service documents year and pagination, not a keyword search.  Matching
    is consequently performed locally over direct metadata after one shared
    source collection, never by fabricating a provider-side query parameter.
    """
    year_text = str(year).strip()
    if not (year_text.isdigit() and len(year_text) == 4):
        raise ValueError("sprtBizYr must be a four-digit year")
    return DiscoveryPlan(
        source="mss_support_program", profile_id="shared_program_pool",
        params={"sprtBizYr": year_text, "pageNo": str(max(1, page_no)), "numOfRows": str(_bounded_rows(rows))},
        shared_scope=f"mss_support_program:{year_text}",
    )


def support_program_matches_profile(item: Mapping[str, Any], profile_id: str) -> bool:
    """Require direct evidence rather than a broad catalogue category label."""
    if profile_id not in SUPPORT_PROGRAM_PROFILES:
        raise ValueError(f"unknown support programme profile: {profile_id}")
    metrics = item.get("metrics_json", item) or {}
    # Deliberately exclude ``categories``.  A broad category can group an
    # unrelated retail or SME programme under a startup umbrella.
    direct_fields = ("title", "purpose", "support_target", "support_type")
    text = " ".join(str(item.get("title") or "") if field == "title" else str(metrics.get(field) or "") for field in direct_fields).casefold()
    return any(term.casefold() in text for term in SUPPORT_PROGRAM_PROFILES[profile_id])


def classify_support_program_profiles(item: Mapping[str, Any]) -> List[str]:
    return [profile_id for profile_id in SUPPORT_PROGRAM_PROFILES if support_program_matches_profile(item, profile_id)]


def support_program_matches_information_types(item: Mapping[str, Any], selected_type_ids: Iterable[str]) -> bool:
    """Use an optional onboarding choice without treating every programme as startup."""
    selected_profiles = {
        SUPPORT_INFORMATION_TYPE_PROFILES[type_id]
        for type_id in selected_type_ids
        if type_id in SUPPORT_INFORMATION_TYPE_PROFILES
    }
    return not selected_profiles or bool(selected_profiles.intersection(classify_support_program_profiles(item)))


def diagnostic_request_budget(source: str) -> Dict[str, int | str]:
    """Return a no-I/O upper bound for a future explicitly approved probe."""
    if source == "public_institution_jobs":
        return {"source": source, "max_requests_per_cycle": PUBLIC_JOBS_MAX_REQUESTS_PER_CYCLE, "max_rows_per_request": MAX_ROWS_PER_REQUEST, "max_candidate_records": PUBLIC_JOBS_MAX_REQUESTS_PER_CYCLE * MAX_ROWS_PER_REQUEST}
    if source == "mss_support_program":
        return {"source": source, "max_requests_per_cycle": MSS_SUPPORT_MAX_REQUESTS_PER_CYCLE, "max_rows_per_request": MAX_ROWS_PER_REQUEST, "max_candidate_records": MSS_SUPPORT_MAX_REQUESTS_PER_CYCLE * MAX_ROWS_PER_REQUEST}
    raise ValueError(f"unsupported source: {source}")


def _official_code_filters(code_filters: Mapping[str, str] | None) -> Dict[str, str]:
    # This function accepts values only after a caller has mapped them from an
    # official code definition.  Its narrow allow-list also keeps unrelated
    # user strings from reaching an API request.
    accepted = ("recrutSe", "hireTypeLst", "ncsCdLst", "workRgnLst")
    return {name: str(value) for name, value in (code_filters or {}).items() if name in accepted and str(value).strip()}


def _bounded_rows(rows: int) -> int:
    return min(MAX_ROWS_PER_REQUEST, max(1, int(rows)))


def _unique(values: Sequence[str]) -> List[str]:
    result: List[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result

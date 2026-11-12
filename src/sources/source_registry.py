import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SourceMetadata:
    source_id: str
    display_name: str
    categories: List[str]
    default_limit: int
    trust_score: float
    freshness_weight: float
    community_weight: float
    enabled_by_default: bool
    description: str


# Source origin is intentionally separate from content language. An
# international source can publish Korean content, and a Korean source can
# report a global event.
SOURCE_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "official_ai_blogs": {"regions": ["international"], "languages": ["en"], "information_types": ["official_update", "industry_news", "research"], "implemented": True, "requires_feed_urls": True, "requires_usage_approval": True},
    "hackernews": {"regions": ["international"], "languages": ["en"], "information_types": ["community", "technology"], "implemented": True},
    "github": {"regions": ["international"], "languages": ["multilingual"], "information_types": ["open_source", "repository"], "implemented": True},
    "youtube": {"regions": ["domestic", "international"], "languages": ["ko", "en", "multilingual"], "information_types": ["video", "creator"], "implemented": True, "requires_env": ["YOUTUBE_API_KEY"]},
    "rss": {"regions": ["domestic", "international"], "languages": ["multilingual"], "information_types": ["news", "official_update", "industry_news", "open_source"], "implemented": True, "requires_feed_urls": True, "requires_usage_approval": True},
    "company_newsroom": {"regions": ["domestic", "international"], "languages": ["multilingual"], "information_types": ["official_update", "industry_news", "press_release"], "implemented": True, "requires_feed_urls": True, "requires_usage_approval": True},
    # Parsers are covered by fixtures, but these feeds must not enter a user
    # feed until reuse/storage and AI-processing terms have been confirmed.
    "geeknews": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["community", "technology", "startup"], "implemented": True, "requires_feed_urls": True, "distribution_status": "permission_review"},
    "kisa_press": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["official_announcement"], "implemented": True, "requires_feed_urls": True, "distribution_status": "permission_review"},
    "kisa_research": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["research_report"], "implemented": True, "requires_feed_urls": True, "distribution_status": "permission_review"},
    "producthunt": {"regions": ["international"], "languages": ["en"], "information_types": ["product_launch"], "implemented": False},
    "reddit": {"regions": ["international"], "languages": ["multilingual"], "information_types": ["community"], "implemented": False},
    "naver_news": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["news", "industry"], "implemented": False, "requires_auth": "NAVER API credentials"},
    "arxiv": {"regions": ["international"], "languages": ["en"], "information_types": ["research"], "implemented": False},
    "crossref": {"regions": ["international"], "languages": ["multilingual"], "information_types": ["research_metadata"], "implemented": True, "requires_env": ["CROSSREF_MAILTO"]},
    "openalex": {"regions": ["international"], "languages": ["multilingual"], "information_types": ["research"], "implemented": True, "requires_usage_approval": True, "requires_env": ["OPENALEX_API_KEY"]},
    "mss_bizinfo": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["startup_program"], "implemented": False, "requires_auth": "공공데이터포털 인증키·이용조건 승인", "distribution_status": "permission_review"},
    "youthcenter_policy": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["youth_policy"], "implemented": False, "requires_auth": "온통청년 인증키·심사 승인", "distribution_status": "permission_review"},
    "tourapi": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["tourism", "event"], "implemented": False, "requires_auth": "공공데이터포털 인증키·운영 이용조건 승인", "distribution_status": "permission_review"},
    "employment24": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["career", "job"], "implemented": False, "requires_auth": "고용24 API 이용 승인", "distribution_status": "permission_review"},
    "opendart": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["disclosure", "finance"], "implemented": False, "requires_auth": "OpenDART 인증키·약관 검토", "distribution_status": "permission_review"},
}

# Service 15113297 is intentionally distinct from the newer 15157820
# Business-Madang feed.  The implementation remains unavailable to runtime
# planning until the issued endpoint, key, and operating approval are recorded.
SOURCE_CAPABILITIES["mss_bizinfo"].update({
    "implemented": True,
    "requires_env": ["MSS_BIZINFO_API_KEY", "MSS_BIZINFO_API_URL"],
    "requires_auth": "data.go.kr service 15113297 key and issued endpoint",
    "service_id": "15113297",
})
# Service 15163956 has a fixture-tested normaliser, but runtime collection is
# intentionally blocked until an operator records the issued JSON schema,
# endpoint, key and a usage approval.  This avoids treating catalogue display
# labels as undocumented wire-field names.
SOURCE_CAPABILITIES["mss_support_program"] = {
    "regions": ["domestic"], "languages": ["ko"],
    "information_types": ["startup_program"], "implemented": True,
    "requires_env": ["PUBLIC_DATA_PORTAL_SERVICE_KEY"],
    "requires_auth": "data.go.kr service 15163956 key and operating approval",
    "service_id": "15163956", "distribution_status": "permission_review",
    "source_kind": "government_support_program", "reliability": "primary",
    "update_cadence": "daily_provider_update", "news_capable": True,
    "schema_status": "official", "ai_processing_status": "metadata_only_pending_operator_review",
    "provider_code_status": "unverified_requires_service_result_code_table",
    "license": "data.go.kr catalogue: unrestricted reuse (confirm current catalogue before activation)",
}
SOURCE_CAPABILITIES.update({
    "public_institution_jobs": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["career", "job"], "implemented": True, "requires_env": ["PUBLIC_DATA_PORTAL_SERVICE_KEY"], "service_id": "15125273", "distribution_status": "permission_review", "schema_status": "official", "provider_code_status": "only_documented_zero_is_accepted", "requires_auth": "data.go.kr service approval and operating policy review", "source_kind": "government_job_data", "ai_processing_status": "metadata_only_pending_policy_review",
        # The catalogue labels the dataset unrestricted, but the portal policy
        # separately excludes third-party rights.  A service-specific approval
        # record and metadata-only operating decision are therefore still
        # required before a user feed can use this source.
        "usage_permissions": {
            "metadata_display": {"state": "permission_review", "evidence_url": "https://www.data.go.kr/data/15125273/openapi.do"},
            "llm_processing": {"state": "not_granted", "evidence_url": "https://www.data.go.kr/data/15125273/openapi.do"},
            "image_or_attachment_use": {"state": "not_in_scope", "evidence_url": "https://www.data.go.kr/ugs/selectPortalPolicyView.do"},
            "production_api_access": {"state": "service_approval_and_operator_record_required", "evidence_url": "https://www.data.go.kr/data/15125273/openapi.do"},
        },
    },
    "public_service_jobs": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["career", "job"], "implemented": True, "requires_env": ["PUBLIC_SERVICE_JOBS_API_KEY", "PUBLIC_SERVICE_JOBS_API_URL"], "service_id": "15156780", "distribution_status": "permission_review", "schema_status": "schema_pending", "requires_auth": "issued operation/model and data.go.kr approval", "source_kind": "government_job_data", "ai_processing_status": "metadata_only_pending_policy_review"},
    "youthcenter_policy": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["youth_policy"], "implemented": True, "requires_env": ["YOUTHCENTER_API_KEY", "YOUTHCENTER_API_URL"], "distribution_status": "permission_review", "schema_status": "schema_pending", "requires_auth": "Youth Center member API approval and issued model", "source_kind": "government_policy", "ai_processing_status": "metadata_only_pending_policy_review"},
    "seoul_culture_events": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["culture_event", "event"], "implemented": True, "requires_env": ["SEOUL_OPEN_DATA_API_KEY", "SEOUL_CULTURE_EVENTS_API_URL"], "service_id": "OA-23041", "distribution_status": "permission_review", "schema_status": "schema_pending", "requires_auth": "Seoul Open Data issued model and usage review", "source_kind": "government_event_data", "ai_processing_status": "metadata_only_pending_policy_review"},
    "employment24": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["career", "job"], "implemented": True, "requires_env": ["WORK24_API_KEY"], "distribution_status": "permission_review", "schema_status": "official", "requires_auth": "Work24 Open API approval", "source_kind": "government_job_data", "ai_processing_status": "metadata_only_pending_policy_review"},
    "opendart": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["disclosure", "finance"], "implemented": True, "requires_env": ["OPENDART_API_KEY"], "distribution_status": "permission_review", "schema_status": "official", "requires_auth": "OpenDART key and terms review", "source_kind": "regulatory_disclosure", "ai_processing_status": "metadata_only_pending_policy_review"},
    "kopis": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["culture_event", "event"], "implemented": True, "requires_env": ["KOPIS_API_KEY"], "distribution_status": "permission_review", "schema_status": "official", "requires_auth": "KOPIS service key and terms review", "source_kind": "performance_schedule", "ai_processing_status": "metadata_only_pending_policy_review"},
})
SOURCE_CAPABILITIES["msit_announcements"] = {
    "regions": ["domestic"], "languages": ["ko"], "information_types": ["government_rnd_announcement", "government_policy", "press_release"],
    "implemented": True, "requires_env": ["MSIT_ANNOUNCEMENT_API_KEY"],
    # data.go.kr service 15074634 declares unrestricted reuse and automatic
    # development/operation approval.  This approval covers the API fields we
    # retain (title, published date, department, and source URL), not an
    # attached document or other linked material.
    "requires_auth": "data.go.kr service 15074634 application",
    "license": "data.go.kr: unrestricted reuse (metadata fields only)",
    "rights_evidence_url": "https://www.data.go.kr/data/15074634/openapi.do",
    "service_id": "15074634",
}
# These are public RSS endpoints, not aliases for the authenticated
# data.go.kr service above.  Keeping separate source ids prevents an operator
# from accidentally treating an RSS validation result as API approval.
SOURCE_CAPABILITIES["msit_business_rss"] = {
    "regions": ["domestic"], "languages": ["ko"],
    "information_types": ["startup_program", "government_rnd_announcement"],
    "implemented": True, "requires_feed_urls": True,
    "requires_usage_approval": True,
    "source_kind": "government_announcement", "reliability": "primary",
    "update_cadence": "event_driven", "news_capable": True,
    "ai_processing_status": "per_item_license_review_required",
    "post_level_rights_required": True,
}
SOURCE_CAPABILITIES["msit_recruitment_rss"] = {
    "regions": ["domestic"], "languages": ["ko"],
    "information_types": ["career", "job"],
    "implemented": True, "requires_feed_urls": True,
    "requires_usage_approval": True,
    "source_kind": "government_job_announcement", "reliability": "primary",
    "update_cadence": "event_driven", "news_capable": True,
    "ai_processing_status": "per_item_license_review_required",
    "post_level_rights_required": True,
}

# Product-facing source fitness.  ``implemented`` answers whether code exists;
# these fields answer the separate questions of what a source actually
# publishes and whether it can be used in an AI-newsletter path.  The catalog
# exposes them without claiming that a permission-review source is live.
SOURCE_CAPABILITIES["official_ai_blogs"].update({
    "source_kind": "official_announcement", "reliability": "primary", "update_cadence": "event_driven",
    "news_capable": True, "ai_processing_status": "source_specific_review_required",
})
SOURCE_CAPABILITIES["company_newsroom"].update({
    "source_kind": "official_announcement", "reliability": "primary", "update_cadence": "event_driven",
    "news_capable": True, "ai_processing_status": "source_specific_review_required",
})
SOURCE_CAPABILITIES["rss"].update({
    "source_kind": "configured_feed", "reliability": "depends_on_feed", "update_cadence": "publisher_defined",
    "news_capable": True, "ai_processing_status": "source_specific_review_required",
})
SOURCE_CAPABILITIES["github"].update({
    "source_kind": "code_repository", "reliability": "primary_for_code", "update_cadence": "event_driven",
    "news_capable": False, "ai_processing_status": "metadata_only_by_default",
})
SOURCE_CAPABILITIES["hackernews"].update({
    "source_kind": "community", "reliability": "secondary", "update_cadence": "continuous",
    "news_capable": False, "ai_processing_status": "review_required",
})
SOURCE_CAPABILITIES["crossref"].update({
    "source_kind": "bibliographic_metadata", "reliability": "primary_for_doi_metadata", "update_cadence": "publisher_deposit",
    "news_capable": False, "ai_processing_status": "metadata_only",
})
SOURCE_CAPABILITIES["openalex"].update({
    "source_kind": "bibliographic_metadata", "reliability": "metadata_index", "update_cadence": "provider_defined",
    "news_capable": False, "ai_processing_status": "metadata_cc0", "license": "CC0",
    "usage_mode": "free_tier_only", "max_results_per_request": 5,
})
SOURCE_CAPABILITIES["tourapi"].update({
    # A fixture-backed parser exists. This remains in permission review, so
    # implemented code is never treated as operational approval.
    "implemented": True,
    "requires_env": ["TOURAPI_SERVICE_KEY"],
    "requires_auth": "data.go.kr service 15101578 key and operating approval",
    "service_id": "15101578",
})
SOURCE_CAPABILITIES["arxiv"].update({
    "source_kind": "research_repository", "reliability": "primary_for_preprints", "update_cadence": "continuous",
    "news_capable": True, "ai_processing_status": "metadata_only_pending_policy",
})
SOURCE_CAPABILITIES["mss_bizinfo"].update({
    "source_kind": "government_announcement", "reliability": "primary", "update_cadence": "real_time",
    "news_capable": True, "ai_processing_status": "approval_and_key_required",
    # The catalogue guarantees title/author/attachment-oriented list data,
    # while the latest isolated response did not establish a publication date,
    # application window, target or detail URL.  Keep it out of the primary
    # "open applications" path until an issued-schema diagnostic proves those
    # fields exist and are reliable.
    "opportunity_discovery_status": "metadata_quality_unverified",
})
SOURCE_CAPABILITIES["msit_announcements"].update({
    "source_kind": "government_announcement", "reliability": "primary", "update_cadence": "event_driven",
    "news_capable": True, "ai_processing_status": "metadata_only_allowed_after_key",
    "attachment_processing_status": "not_authorized_by_source_metadata_license",
})
SOURCE_CAPABILITIES["employment24"].update({
    "source_kind": "government_job_data", "reliability": "primary", "update_cadence": "real_time",
    "news_capable": True, "ai_processing_status": "license_review_required",
})
SOURCE_CAPABILITIES["opendart"].update({
    "source_kind": "regulatory_disclosure", "reliability": "primary", "update_cadence": "filing_driven",
    "news_capable": True, "ai_processing_status": "terms_and_key_required",
    # The OpenDART introduction permits structured disclosure data to be used
    # by individuals, businesses and institutions.  It does not expressly
    # grant a third-party LLM-processing permission, so that scope stays
    # separate from ordinary metadata display.
    "usage_permissions": {
        "metadata_display": {"state": "allowed_with_source_link", "evidence_url": "https://opendart.fss.or.kr/intro/main.do"},
        "llm_processing": {"state": "permission_review", "evidence_url": "https://opendart.fss.or.kr/intro/terms.do"},
        "image_or_attachment_use": {"state": "not_in_scope", "evidence_url": "https://opendart.fss.or.kr/intro/terms.do"},
        "production_api_access": {"state": "account_registration_and_quota_required", "evidence_url": "https://opendart.fss.or.kr/intro/terms.do"},
    },
    # This is an operator attestation recorded from the service owner, not a
    # replacement for a retained registration screen or an approved runtime
    # configuration.  Activation code must continue to require an explicit
    # non-secret evidence reference.
    "operator_confirmations": {
        "service_registration": {
            "state": "user_confirmed",
            "confirmed_on": "2026-11-10",
            "facts": (
                "registered service URL matches LUMOS",
                "registered purpose matches LUMOS",
            ),
            "document_evidence_recorded": False,
            "activation_sufficient": False,
        },
    },
})
SOURCE_CAPABILITIES["youthcenter_policy"].update({
    "source_kind": "government_policy", "reliability": "primary", "update_cadence": "provider_defined",
    "news_capable": True, "ai_processing_status": "endpoint_and_license_review_required",
})
SOURCE_CAPABILITIES["tourapi"].update({
    "source_kind": "government_event_data", "reliability": "primary", "update_cadence": "real_time",
    "news_capable": True, "ai_processing_status": "approval_and_key_required",
    # The catalogue's unrestricted-use/web-service scope covers the small
    # metadata card only.  It does not turn photos or external LLM processing
    # into a granted right, and production traffic still needs KTO review.
    "usage_permissions": {
        "metadata_display": {"state": "allowed_with_attribution", "evidence_url": "https://www.data.go.kr/data/15101578/openapi.do"},
        "llm_processing": {"state": "not_granted", "evidence_url": "https://www.data.go.kr/data/15101578/openapi.do"},
        "image_or_attachment_use": {"state": "per_item_license_required", "evidence_url": "https://www.data.go.kr/data/15101578/openapi.do"},
        "production_api_access": {"state": "operating_account_approval_required", "evidence_url": "https://www.data.go.kr/data/15101578/openapi.do"},
    },
})


def source_usage_permission(source_id: str, scope: str) -> Dict[str, Any]:
    """Return a scope decision without treating it as source activation.

    A source must still pass ``source_availability`` and its global
    ``distribution_status`` gate before any runtime collection can occur.
    """
    if scope not in {"metadata_display", "llm_processing", "image_or_attachment_use", "production_api_access"}:
        raise ValueError(f"unknown permission scope: {scope}")
    capability = SOURCE_CAPABILITIES.get(source_id, {})
    permission = dict((capability.get("usage_permissions") or {}).get(scope) or {})
    return {"source_id": source_id, "scope": scope, "state": permission.get("state", "not_assessed"), "evidence_url": permission.get("evidence_url")}


def is_limited_opendart_pilot(config: Optional[Dict[str, Any]] = None) -> bool:
    """Recognise the narrow, per-user metadata Pilot without global approval.

    The runtime additionally verifies the user ID against its process-level
    allowlist.  This marker can never make the Registry-wide permission state
    approved or authorize LLM/full-text processing.
    """
    config = dict(config or {})
    return bool(
        config.get("pilot_mode") == "single_user_metadata_only"
        and int(config.get("pilot_user_id") or 0) > 0
        and str(config.get("pilot_approval_reference") or "").strip()
        and config.get("metadata_card_publish_approved") is True
    )


def source_operator_confirmation(source_id: str, topic: str) -> Dict[str, Any]:
    """Return a non-secret operator attestation without granting activation.

    This deliberately distinguishes what the service owner confirmed from a
    document reference that an operator records before enabling production
    traffic.
    """
    capability = SOURCE_CAPABILITIES.get(source_id, {})
    confirmation = dict((capability.get("operator_confirmations") or {}).get(topic) or {})
    return {
        "source_id": source_id,
        "topic": topic,
        "state": confirmation.get("state", "not_recorded"),
        "confirmed_on": confirmation.get("confirmed_on"),
        "facts": list(confirmation.get("facts") or ()),
        "document_evidence_recorded": bool(confirmation.get("document_evidence_recorded")),
        "activation_sufficient": bool(confirmation.get("activation_sufficient")),
    }

# Evidence-backed feed policy records. These are deliberately a registry of
# review outcomes, not a switch that activates a feed in local-live. An item
# can only be configured with ``usage_status=approved`` after its policy and
# operator approval match the requested processing scope.
OFFICIAL_AI_TREND_FEEDS: Dict[str, Dict[str, Any]] = {
    "msit_press": {
        "display_name": "MSIT Press Releases",
        "feed_url": "https://www.msit.go.kr/user/rss/rss.do?bbsSeqNo=94",
        "source_type": "government_press_release",
        "information_types": ["press_release", "government_policy", "industry_news"],
        "evidence_url": "https://www.msit.go.kr/contents/cont.do?mId=173&mPid=147&sCode=user",
        "rights_evidence_url": "https://www.msit.go.kr/bbs/view.do?bbsSeqNo=94&mId=307&mPid=208&nttSeqNo=3187715",
        "metadata_storage": "allowed_for_validation",
        "excerpt_storage": "per_item_license_required",
        "ai_summary": "per_item_license_required",
        "user_summary_delivery": "per_item_license_required",
        "image_reuse": "per_item_license_required",
        "activation_state": "policy_review_required",
    },
    "openai_news": {
        "display_name": "OpenAI News",
        "feed_url": "https://openai.com/news/rss.xml",
        "source_type": "company_newsroom",
        "information_types": ["official_update", "industry_news"],
        "evidence_url": "https://openai.com/policies/terms-of-use/",
        "metadata_storage": "not_explicitly_granted",
        "excerpt_storage": "not_granted",
        "ai_summary": "not_granted",
        "user_summary_delivery": "not_granted",
        "image_reuse": "not_granted",
        "activation_state": "permission_review",
    },
    "google_blog": {
        "display_name": "Google Official Blog",
        "feed_url": "https://blog.google/rss/",
        "source_type": "company_newsroom",
        "information_types": ["official_update", "industry_news"],
        "evidence_url": "https://policies.google.com/terms",
        "metadata_storage": "not_explicitly_granted",
        "excerpt_storage": "not_granted",
        "ai_summary": "not_granted",
        "user_summary_delivery": "not_granted",
        "image_reuse": "not_granted",
        "activation_state": "permission_review",
    },
    "msit_business_rss": {
        "display_name": "MSIT Business Announcements RSS",
        "feed_url": "https://www.msit.go.kr/user/rss/rss.do?bbsSeqNo=100",
        "source_type": "government_announcement",
        "information_types": ["startup_program", "government_rnd_announcement"],
        "evidence_url": "https://www.msit.go.kr/contents/cont.do?mId=327&mPid=147&sCode=user",
        "rights_evidence_url": "https://www.msit.go.kr/contents/cont.do?mId=173&mPid=147&sCode=user",
        "metadata_storage": "allowed_for_validation_only",
        "excerpt_storage": "per_item_license_required",
        "ai_summary": "per_item_license_required",
        "user_summary_delivery": "per_item_license_required",
        "image_reuse": "per_item_license_required",
        "activation_state": "permission_review",
    },
    "msit_recruitment_rss": {
        "display_name": "MSIT Recruitment RSS",
        "feed_url": "https://www.msit.go.kr/user/rss/rss.do?bbsSeqNo=98",
        "source_type": "government_job_announcement",
        "information_types": ["career", "job"],
        "evidence_url": "https://www.msit.go.kr/contents/cont.do?mId=327&mPid=147&sCode=user",
        "rights_evidence_url": "https://www.msit.go.kr/contents/cont.do?mId=173&mPid=147&sCode=user",
        "metadata_storage": "allowed_for_validation_only",
        "excerpt_storage": "per_item_license_required",
        "ai_summary": "per_item_license_required",
        "user_summary_delivery": "per_item_license_required",
        "image_reuse": "per_item_license_required",
        "activation_state": "permission_review",
    },
}


def _legacy_source_availability(source_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    capability = SOURCE_CAPABILITIES.get(source_id, {})
    if not capability.get("implemented", False):
        return {"available": False, "reason": "아직 연결 준비 중이에요.", "capabilities": capability}
    if capability.get("distribution_status") == "permission_review":
        return {"available": False, "reason": "이용 조건 확인이 끝나기 전까지 사용자 피드에 공개하지 않아요.", "capabilities": capability}
    missing_env = [name for name in capability.get("requires_env", []) if not os.environ.get(name, "").strip()]
    if missing_env:
        return {"available": False, "reason": f"{' / '.join(missing_env)} 설정이 필요해요.", "capabilities": capability}
    if capability.get("requires_feed_urls") and not (config or {}).get("feed_urls"):
        return {"available": False, "reason": "RSS 주소를 먼저 추가해주세요.", "capabilities": capability}
    return {"available": True, "reason": "사용할 수 있어요.", "capabilities": capability}


def source_availability(source_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return a machine-readable readiness state as well as display text."""
    capability = SOURCE_CAPABILITIES.get(source_id, {})
    if not capability:
        return {"available": False, "state": "unregistered", "reason": "Source is not registered.", "capabilities": {}}
    if not capability.get("implemented", False):
        return {**_legacy_source_availability(source_id, config), "state": "collector_pending"}
    if capability.get("distribution_status") == "permission_review":
        if source_id == "opendart" and is_limited_opendart_pilot(config):
            missing_env = [name for name in capability.get("requires_env", []) if not os.environ.get(name, "").strip()]
            if not missing_env:
                return {
                    "available": True,
                    "state": "limited_pilot_metadata_only",
                    "reason": "Explicit one-user OpenDART metadata Pilot only.",
                    "capabilities": capability,
                }
        return {**_legacy_source_availability(source_id, config), "state": "permission_review"}
    if capability.get("requires_usage_approval") and (config or {}).get("usage_status") != "approved":
        return {"available": False, "state": "permission_review", "reason": "Source-specific reuse and AI-processing approval is required.", "capabilities": capability}
    missing_env = [name for name in capability.get("requires_env", []) if not os.environ.get(name, "").strip()]
    if missing_env:
        return {**_legacy_source_availability(source_id, config), "state": "configuration_required"}
    if capability.get("requires_feed_urls") and not (config or {}).get("feed_urls"):
        return {**_legacy_source_availability(source_id, config), "state": "configuration_required"}
    return {**_legacy_source_availability(source_id, config), "state": "available"}


SOURCE_REGISTRY: Dict[str, SourceMetadata] = {
    "official_ai_blogs": SourceMetadata(
        source_id="official_ai_blogs",
        display_name="Official AI Blogs",
        categories=["AI_LLM_AGENT", "RESEARCH"],
        default_limit=5,
        trust_score=0.95,
        freshness_weight=0.8,
        community_weight=0.2,
        enabled_by_default=True,
        description="High-trust official AI product and research updates.",
    ),
    "hackernews": SourceMetadata(
        source_id="hackernews",
        display_name="Hacker News",
        categories=["AI_LLM_AGENT", "STARTUP_PRODUCT", "DEVELOPER_TECH"],
        default_limit=8,
        trust_score=0.75,
        freshness_weight=0.75,
        community_weight=0.9,
        enabled_by_default=True,
        description="Developer and startup community reaction.",
    ),
    "github": SourceMetadata(
        source_id="github",
        display_name="GitHub",
        categories=["AI_LLM_AGENT", "DEVELOPER_TECH", "RESEARCH", "COMPANY_TRACKING"],
        default_limit=8,
        trust_score=0.8,
        freshness_weight=0.7,
        community_weight=0.75,
        enabled_by_default=True,
        description="Implementation movement across open source repositories.",
    ),
    "producthunt": SourceMetadata(
        source_id="producthunt",
        display_name="Product Hunt",
        categories=["STARTUP_PRODUCT"],
        default_limit=6,
        trust_score=0.65,
        freshness_weight=0.85,
        community_weight=0.8,
        enabled_by_default=False,
        description="New products, launches, and competitive discovery.",
    ),
    "reddit": SourceMetadata(
        source_id="reddit",
        display_name="Reddit",
        categories=["AI_LLM_AGENT", "STARTUP_PRODUCT", "DEVELOPER_TECH", "CONTENT_SNS", "CAREER"],
        default_limit=6,
        trust_score=0.45,
        freshness_weight=0.65,
        community_weight=0.85,
        enabled_by_default=False,
        description="Community reaction with higher noise.",
    ),
    "youtube": SourceMetadata(
        source_id="youtube",
        display_name="YouTube",
        categories=["CONTENT_SNS", "CAREER"],
        default_limit=5,
        trust_score=0.55,
        freshness_weight=0.6,
        community_weight=0.75,
        enabled_by_default=False,
        description="Creator and video trend signals.",
    ),
    "naver_news": SourceMetadata(
        source_id="naver_news",
        display_name="Naver News",
        categories=["DOMESTIC_INDUSTRY", "COMPANY_TRACKING", "CAREER"],
        default_limit=7,
        trust_score=0.7,
        freshness_weight=0.85,
        community_weight=0.35,
        enabled_by_default=False,
        description="Korean industry, company, and career news.",
    ),
    "rss": SourceMetadata(
        source_id="rss",
        display_name="RSS and Official Blogs",
        categories=["STARTUP_PRODUCT", "DEVELOPER_TECH", "CONTENT_SNS", "DOMESTIC_INDUSTRY", "COMPANY_TRACKING", "CAREER"],
        default_limit=8,
        trust_score=0.7,
        freshness_weight=0.75,
        community_weight=0.25,
        enabled_by_default=True,
        description="Configured feeds and official changelogs.",
    ),
    "arxiv": SourceMetadata(
        source_id="arxiv",
        display_name="arXiv",
        categories=["AI_LLM_AGENT", "RESEARCH"],
        default_limit=5,
        trust_score=0.85,
        freshness_weight=0.65,
        community_weight=0.25,
        enabled_by_default=False,
        description="Research and paper signals.",
    ),
    "crossref": SourceMetadata(
        source_id="crossref", display_name="Crossref", categories=["RESEARCH"], default_limit=8,
        trust_score=.85, freshness_weight=.7, community_weight=.05, enabled_by_default=False,
        description="Publisher-deposited research metadata and DOI records.",
    ),
    "openalex": SourceMetadata(
        source_id="openalex", display_name="OpenAlex", categories=["RESEARCH"], default_limit=5,
        trust_score=.85, freshness_weight=.75, community_weight=.05, enabled_by_default=False,
        description="CC0 scholarly-work metadata for research discovery; never a general news source.",
    ),
    "mss_bizinfo": SourceMetadata(
        source_id="mss_bizinfo", display_name="중소벤처기업 지원사업", categories=["STARTUP_PROGRAM"], default_limit=8,
        trust_score=.9, freshness_weight=.9, community_weight=.05, enabled_by_default=False,
        description="Official startup and SME support announcements; approval required.",
    ),
    "mss_support_program": SourceMetadata(
        source_id="mss_support_program", display_name="MSS Distribution Support Programs", categories=["STARTUP_PROGRAM"], default_limit=8,
        trust_score=.9, freshness_weight=.9, community_weight=.05, enabled_by_default=False,
        description="Official SME and small-business support programmes; issued schema and operator approval required.",
    ),
    "public_institution_jobs": SourceMetadata(source_id="public_institution_jobs", display_name="Public Institution Jobs", categories=["CAREER"], default_limit=8, trust_score=.9, freshness_weight=.9, community_weight=.05, enabled_by_default=False, description="Public-institution recruitment notices; issued schema required."),
    "public_service_jobs": SourceMetadata(source_id="public_service_jobs", display_name="Public Service Jobs", categories=["CAREER"], default_limit=8, trust_score=.9, freshness_weight=.9, community_weight=.05, enabled_by_default=False, description="Public-sector recruitment notices; issued schema required."),
    "seoul_culture_events": SourceMetadata(source_id="seoul_culture_events", display_name="Seoul Culture Events", categories=["CULTURE_TRAVEL_EVENT"], default_limit=8, trust_score=.85, freshness_weight=.85, community_weight=.05, enabled_by_default=False, description="Seoul cultural events; issued schema required."),
    "kopis": SourceMetadata(source_id="kopis", display_name="KOPIS", categories=["CULTURE_TRAVEL_EVENT"], default_limit=8, trust_score=.9, freshness_weight=.85, community_weight=.05, enabled_by_default=False, description="Official performance schedules; service key and policy review required."),
    "youthcenter_policy": SourceMetadata(
        source_id="youthcenter_policy", display_name="온통청년", categories=["YOUTH_POLICY"], default_limit=8,
        trust_score=.9, freshness_weight=.85, community_weight=.05, enabled_by_default=False,
        description="Official youth policy and youth-space information; approval required.",
    ),
    "tourapi": SourceMetadata(
        source_id="tourapi", display_name="한국관광공사 TourAPI", categories=["CULTURE_TRAVEL_EVENT"], default_limit=8,
        trust_score=.85, freshness_weight=.85, community_weight=.1, enabled_by_default=False,
        description="Official tourism, festival, and regional event information; approval required.",
    ),
    "employment24": SourceMetadata(
        source_id="employment24", display_name="고용24", categories=["CAREER"], default_limit=8,
        trust_score=.9, freshness_weight=.9, community_weight=.05, enabled_by_default=False,
        description="Official employment and career information; approval required.",
    ),
    "opendart": SourceMetadata(
        source_id="opendart", display_name="OpenDART", categories=["ECONOMY_FINANCE"], default_limit=8,
        trust_score=.95, freshness_weight=.9, community_weight=.05, enabled_by_default=False,
        description="Official corporate disclosures and finance facts; approval required.",
    ),
    "msit_announcements": SourceMetadata(
        source_id="msit_announcements", display_name="MSIT Business Announcements", categories=["STARTUP_PROGRAM", "INDUSTRY_POLICY", "RESEARCH"], default_limit=8,
        trust_score=.9, freshness_weight=.85, community_weight=.05, enabled_by_default=False,
        description="Official MSIT R&D, international-cooperation, and infrastructure calls; approval required.",
    ),
    "msit_business_rss": SourceMetadata(
        source_id="msit_business_rss", display_name="MSIT Business Announcements RSS",
        categories=["STARTUP_PROGRAM", "INDUSTRY_POLICY"], default_limit=6,
        trust_score=.9, freshness_weight=.85, community_weight=.05, enabled_by_default=False,
        description="MSIT business-announcement RSS; reuse and AI processing require review.",
    ),
    "msit_recruitment_rss": SourceMetadata(
        source_id="msit_recruitment_rss", display_name="MSIT Recruitment RSS",
        categories=["CAREER"], default_limit=6,
        trust_score=.9, freshness_weight=.85, community_weight=.05, enabled_by_default=False,
        description="MSIT recruitment RSS; reuse and AI processing require review.",
    ),
    "company_newsroom": SourceMetadata(
        source_id="company_newsroom",
        display_name="Company Newsrooms",
        categories=["DOMESTIC_INDUSTRY", "COMPANY_TRACKING"],
        default_limit=5,
        trust_score=0.85,
        freshness_weight=0.8,
        community_weight=0.2,
        enabled_by_default=False,
        description="Company announcements and official updates.",
    ),
    "geeknews": SourceMetadata(
        source_id="geeknews", display_name="GeekNews", categories=["DEVELOPER_TECH", "STARTUP_PRODUCT"],
        default_limit=6, trust_score=0.6, freshness_weight=0.7, community_weight=0.8,
        enabled_by_default=False, description="Korean developer, technology, and startup community links.",
    ),
    "kisa_press": SourceMetadata(
        source_id="kisa_press", display_name="KISA 보도자료", categories=["SECURITY_PRIVACY", "DOMESTIC_INDUSTRY"],
        default_limit=5, trust_score=0.9, freshness_weight=0.8, community_weight=0.1,
        enabled_by_default=False, description="Korea Internet & Security Agency official press releases.",
    ),
    "kisa_research": SourceMetadata(
        source_id="kisa_research", display_name="KISA 연구보고서", categories=["SECURITY_PRIVACY", "RESEARCH"],
        default_limit=5, trust_score=0.9, freshness_weight=0.6, community_weight=0.1,
        enabled_by_default=False, description="Korea Internet & Security Agency research reports.",
    ),
}


def get_source(source_id: str) -> SourceMetadata:
    return SOURCE_REGISTRY[source_id]


def list_sources() -> List[SourceMetadata]:
    return list(SOURCE_REGISTRY.values())


def get_source_catalog(configs: Optional[List[Dict[str, Any]]] = None, status_lookup=None) -> List[Dict[str, Any]]:
    config_map = {item["source_id"]: item for item in configs or []}
    catalog = []
    for source_id, metadata in SOURCE_REGISTRY.items():
        config = config_map.get(source_id, {})
        item = asdict(metadata)
        item["current_enabled"] = bool(config.get("enabled", metadata.enabled_by_default))
        item["selection_mode"] = config.get("selection_mode", "auto")
        item["priority"] = int(config.get("priority", 50))
        item["config_json"] = config.get("config_json", {})
        availability = source_availability(source_id, item["config_json"])
        item["available"] = availability["available"]
        item["availability_reason"] = availability["reason"]
        item["capabilities"] = availability["capabilities"]
        item["implemented_status"] = status_lookup(source_id) if status_lookup else "unknown"
        catalog.append(item)
    return sorted(catalog, key=lambda item: (not item["current_enabled"], -item["priority"], item["source_id"]))


def get_effective_source_config(source_id: str, configs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    metadata = SOURCE_REGISTRY[source_id]
    config_map = {item["source_id"]: item for item in configs or []}
    config = config_map.get(source_id, {})
    return {
        **asdict(metadata),
        "enabled": bool(config.get("enabled", metadata.enabled_by_default)),
        "priority": int(config.get("priority", 50)),
        "config_json": config.get("config_json", {}),
    }


def list_enabled_sources(configs: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    return [
        item["source_id"]
        for item in get_source_catalog(configs)
        if item["current_enabled"]
    ]

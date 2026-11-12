"""Read-only readiness checks and bounded canary specifications.

This module never changes registry state and never makes a request.  It keeps
the evidence an operator must record separate from an API key's mere presence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Mapping

from src.sources.collectors.base import SourceQuery
from src.sources.source_registry import source_operator_confirmation, source_usage_permission


@dataclass(frozen=True)
class CanarySpec:
    source: str
    max_requests: int
    max_items: int
    max_retries: int
    query: SourceQuery
    metadata_fields: tuple[str, ...]
    llm_allowed: bool = False


_SOURCE_POLICIES = {
    "public_institution_jobs": {
        "env": "PUBLIC_INSTITUTION_JOBS_API_KEY|PUBLIC_DATA_PORTAL_SERVICE_KEY",
        # This is intentionally list-only. The public page does not expose a
        # field-level /detail model, so an announcement query bound must never
        # be presented as an application deadline.
        "fields": (
            "recruitment_title", "institution_name", "job_type", "region",
            "announcement_start_at", "official_url",
        ),
        "daily_canary_budget": 1,
    },
    "tourapi": {
        "env": "TOURAPI_SERVICE_KEY",
        "fields": ("title", "event_start_at", "event_end_at", "region", "venue", "official_url"),
        "daily_canary_budget": 1,
        # A previously exposed key must be rotated before even an isolated
        # canary can use it. Store only an operator evidence reference, never
        # the credential or its fingerprint.
        "requires_credential_rotation_evidence": True,
    },
    "opendart": {
        "env": "OPENDART_API_KEY",
        "fields": ("company_name", "disclosure_name", "receipt_at", "official_url"),
        "daily_canary_budget": 1,
        # Account registration includes the declared service URL and purpose.
        "requires_service_registration_evidence": True,
    },
}


def activation_readiness(source: str, config: Mapping[str, Any] | None = None, *, env_configured: bool = False) -> Dict[str, Any]:
    """Return activation and isolated-canary checklists without activating a source.

    ``isolated_canary_*`` inputs are deliberately ephemeral operator attestations.
    They can permit one approved diagnostic request, but never satisfy the
    production activation decision or alter Registry state.
    """
    if source not in _SOURCE_POLICIES:
        raise ValueError(f"unsupported operational source: {source}")
    config = dict(config or {})
    metadata = source_usage_permission(source, "metadata_display")
    production = source_usage_permission(source, "production_api_access")
    llm = source_usage_permission(source, "llm_processing")
    image = source_usage_permission(source, "image_or_attachment_use")
    registration_confirmation = source_operator_confirmation(source, "service_registration")
    evidence = str(config.get("production_api_access_evidence") or "").strip()
    rotation_evidence = str(config.get("credential_rotation_evidence") or "").strip()
    registration_evidence = str(config.get("service_registration_evidence") or "").strip()
    isolated_canary_authorized = bool(config.get("isolated_canary_authorized"))
    legacy_credential_exception = bool(
        source == "tourapi"
        and config.get("isolated_canary_existing_credential_exception")
    )
    # A local key alone cannot satisfy an operating-account review.
    production_evidence_recorded = bool(evidence)
    credential_rotation_evidence_recorded = bool(rotation_evidence)
    service_registration_evidence_recorded = bool(registration_evidence)
    rotation_ok = (
        credential_rotation_evidence_recorded
        if _SOURCE_POLICIES[source].get("requires_credential_rotation_evidence")
        else True
    )
    registration_ok = (
        service_registration_evidence_recorded
        if _SOURCE_POLICIES[source].get("requires_service_registration_evidence")
        else True
    )
    canary_rotation_ok = rotation_ok or legacy_credential_exception
    ready = bool(
        env_configured
        and metadata["state"].startswith("allowed")
        and production["state"] in {"allowed", "allowed_with_attribution"}
        and production_evidence_recorded
        and rotation_ok
        and registration_ok
    )
    # Production API scope remains a Registry/document-evidence decision.
    # An explicit, one-off operator authorisation is enough only for a
    # diagnostic Canary and must be supplied again for each invocation.
    ready_for_canary = bool(
        env_configured
        and metadata["state"].startswith("allowed")
        and isolated_canary_authorized
        and canary_rotation_ok
    )
    return {
        "source": source,
        "metadata_display": metadata,
        "production_api_access": production,
        "llm_processing": llm,
        "image_or_attachment_use": image,
        "env_configured": bool(env_configured),
        "production_evidence_recorded": production_evidence_recorded,
        "credential_rotation_evidence_recorded": credential_rotation_evidence_recorded,
        "service_registration_evidence_recorded": service_registration_evidence_recorded,
        "service_registration_user_confirmed": registration_confirmation["state"] == "user_confirmed",
        "service_registration_document_evidence_recorded": registration_confirmation["document_evidence_recorded"],
        "isolated_canary_authorized": isolated_canary_authorized,
        "legacy_credential_exception_used": legacy_credential_exception,
        "ready_for_canary": ready_for_canary,
        "ready_for_activation": ready,
        "daily_canary_budget": _SOURCE_POLICIES[source]["daily_canary_budget"],
    }


def canary_spec(source: str, *, today: date, company_name: str = "") -> CanarySpec:
    """Build the post-approval single-request query; it does not execute it."""
    if source == "tourapi":
        return CanarySpec(
            source=source, max_requests=1, max_items=10, max_retries=0,
            query=SourceQuery(source=source, query="", params={"event_start_date": today.strftime("%Y%m%d")}),
            metadata_fields=_SOURCE_POLICIES[source]["fields"],
        )
    if source == "public_institution_jobs":
        # ``recrutPbancTtl`` is the documented free-text condition. Code
        # filters remain absent until an operator supplies a versioned official
        # code definition. ``pbancEndYmd`` is deliberately absent because it
        # bounds announcement start-date searches, not application deadlines.
        return CanarySpec(
            source=source, max_requests=1, max_items=10, max_retries=0,
            query=SourceQuery(
                source=source,
                query="\uc778\ud134",
                params={
                    "raw_interest": "\uc778\ud134",
                    "recrutPbancTtl": "\uc778\ud134",
                    "ongoingYn": "Y",
                    "resultType": "json",
                    "pageNo": 1,
                    "direct_evidence_terms": ("\uc778\ud134", "intern"),
                    "collection_scope": "public_jobs_metadata_canary",
                },
            ),
            metadata_fields=_SOURCE_POLICIES[source]["fields"],
        )
    if source == "opendart":
        company = str(company_name).strip()
        if not company:
            raise ValueError("OpenDART canary requires an explicit tracked company")
        return CanarySpec(
            source=source, max_requests=1, max_items=10, max_retries=0,
            query=SourceQuery(source=source, query=company, params={
                "raw_interest": company, "company_name": company,
                "bgn_de": (today - timedelta(days=1)).strftime("%Y%m%d"),
                "end_de": today.strftime("%Y%m%d"),
                "page_count": 10,
            }),
            metadata_fields=_SOURCE_POLICIES[source]["fields"],
        )
    raise ValueError(f"unsupported operational source: {source}")

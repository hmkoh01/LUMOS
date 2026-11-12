from datetime import date

import pytest

from src.sources.operational_canary import activation_readiness, canary_spec
from src.sources.source_registry import source_operator_confirmation
from src.sources.source_registry import source_availability


def test_tourapi_metadata_is_separate_from_unapproved_production_access():
    readiness = activation_readiness("tourapi", env_configured=True)
    assert readiness["metadata_display"]["state"] == "allowed_with_attribution"
    assert readiness["production_api_access"]["state"] == "operating_account_approval_required"
    assert readiness["llm_processing"]["state"] == "not_granted"
    assert readiness["ready_for_activation"] is False
    assert readiness["credential_rotation_evidence_recorded"] is False


def test_opendart_requires_registered_account_and_keeps_llm_out_of_scope():
    readiness = activation_readiness("opendart", env_configured=True)
    assert readiness["metadata_display"]["state"] == "allowed_with_source_link"
    assert readiness["production_api_access"]["state"] == "account_registration_and_quota_required"
    assert readiness["llm_processing"]["state"] == "permission_review"
    assert readiness["ready_for_activation"] is False
    assert readiness["service_registration_evidence_recorded"] is False
    assert readiness["service_registration_user_confirmed"] is True
    assert readiness["service_registration_document_evidence_recorded"] is False


def test_opendart_user_confirmation_is_not_documentary_activation_evidence():
    confirmation = source_operator_confirmation("opendart", "service_registration")
    assert confirmation["state"] == "user_confirmed"
    assert confirmation["document_evidence_recorded"] is False
    assert confirmation["activation_sufficient"] is False


def test_opendart_limited_pilot_does_not_change_global_permission_review(monkeypatch):
    monkeypatch.setenv("OPENDART_API_KEY", "fixture")
    config = {
        "pilot_mode": "single_user_metadata_only",
        "pilot_user_id": 454,
        "pilot_approval_reference": "local-owner-approval-2026-11-10",
        "metadata_card_publish_approved": True,
    }
    state = source_availability("opendart", config)
    assert state["available"] is True
    assert state["state"] == "limited_pilot_metadata_only"
    assert source_availability("opendart", {})["state"] == "permission_review"


def test_canary_readiness_requires_non_secret_rotation_and_registration_evidence():
    tour = activation_readiness("tourapi", {
        "production_api_access_evidence": "operator-ticket",
    }, env_configured=True)
    assert tour["credential_rotation_evidence_recorded"] is False
    assert tour["ready_for_activation"] is False

    dart = activation_readiness("opendart", {
        "production_api_access_evidence": "registration-ticket",
    }, env_configured=True)
    assert dart["service_registration_evidence_recorded"] is False
    assert dart["ready_for_activation"] is False


def test_tourapi_existing_credential_exception_is_canary_only_not_activation():
    readiness = activation_readiness("tourapi", {
        "isolated_canary_authorized": True,
        "isolated_canary_existing_credential_exception": True,
    }, env_configured=True)
    assert readiness["legacy_credential_exception_used"] is True
    assert readiness["ready_for_canary"] is True
    assert readiness["ready_for_activation"] is False


def test_canary_specs_are_single_request_metadata_only_and_dont_guess_a_company():
    today = date(2026, 11, 9)
    tour = canary_spec("tourapi", today=today)
    assert (tour.max_requests, tour.max_items, tour.max_retries, tour.llm_allowed) == (1, 10, 0, False)
    assert tour.query.params["event_start_date"] == "20261109"
    with pytest.raises(ValueError):
        canary_spec("opendart", today=today)
    dart = canary_spec("opendart", today=today, company_name="Example Corp")
    assert dart.query.params["bgn_de"] == "20261108"
    assert dart.query.params["end_de"] == "20261109"
    assert dart.query.query == "Example Corp"

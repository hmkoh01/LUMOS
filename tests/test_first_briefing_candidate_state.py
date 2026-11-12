from src.engine.collection.source_support import first_briefing_candidate_state
from src.engine.collection.source_support import collection_support


def test_first_briefing_distinguishes_candidates_empty_pool_and_no_operational_source():
    supported = {"status": "supported"}
    blocked = {"status": "awaiting_approved_source"}
    assert first_briefing_candidate_state(supported, 2) == "candidates_available"
    assert first_briefing_candidate_state(supported, 0) == "no_matching_candidates"
    assert first_briefing_candidate_state(supported) == "collection_pending"
    assert first_briefing_candidate_state(supported, collection_observed=True) == "no_matching_candidates"
    assert first_briefing_candidate_state(blocked, 0) == "no_operational_source"


def test_verified_company_identity_routes_only_the_exact_named_interest_to_opendart(monkeypatch):
    monkeypatch.setattr("src.engine.collection.source_support.source_availability", lambda source, _config: {
        "available": source == "opendart", "state": "limited_pilot_metadata_only",
    })
    configs = [{"source_id": "opendart", "config_json": {
        "verified_company_identities": [{"interest": "SK hynix", "stock_code": "000660"}],
    }}]
    supported = collection_support("SK hynix", ["opendart"], configs)
    assert supported["sources"] == ["opendart"]
    assert first_briefing_candidate_state(supported, collection_observed=True) == "no_matching_candidates"
    assert collection_support("general economy", ["opendart"], configs)["sources"] == []

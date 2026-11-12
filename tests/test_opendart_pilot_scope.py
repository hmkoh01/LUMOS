from src.engine.config import CollectionConfig, EngineConfig
from src.engine.collection.source_support import collection_support
from src.engine.operations import EngineOperations


class _Store:
    def get_enabled_source_configs(self, *, user_id):
        return [{"source_id": "opendart", "config_json": {}}]


def _operations_for(config):
    # The scope gate is pure planning logic. Avoid constructing runtime
    # workers or a queue while testing it.
    operations = object.__new__(EngineOperations)
    operations.store = _Store()
    operations.config = config
    return operations


def test_opendart_pilot_is_fail_closed_without_an_explicit_user_allowlist(monkeypatch):
    monkeypatch.setattr("src.engine.operations.source_availability", lambda *_: {"available": True})
    config = EngineConfig(enabled=True, collection=CollectionConfig(pilot_sources=("opendart",)))
    assert _operations_for(config)._enabled_pilot_sources({17}) == []


def test_opendart_pilot_allows_only_the_named_single_test_user(monkeypatch):
    monkeypatch.setattr("src.engine.operations.source_availability", lambda *_: {"available": True})
    collection = CollectionConfig(pilot_sources=("opendart",), opendart_pilot_user_ids=(17,))
    operations = _operations_for(EngineConfig(enabled=True, collection=collection))
    assert operations._enabled_pilot_sources({18}) == []
    assert operations._enabled_pilot_sources({17}) == ["opendart"]


def test_verified_korean_company_interest_matches_without_console_encoding_loss(monkeypatch):
    """Company identity matching operates on Python Unicode, not a console code page."""
    monkeypatch.setattr(
        "src.engine.collection.source_support.source_availability",
        lambda *_: {"available": True, "state": "limited_pilot_metadata_only"},
    )
    company_interest = "\u0053\u004b\ud558\uc774\ub2c9\uc2a4"
    support = collection_support(
        company_interest,
        ("opendart",),
        [{
            "source_id": "opendart",
            "config_json": {
                "verified_company_identities": [{
                    "interest": company_interest,
                    "stock_code": "000660",
                }],
            },
        }],
    )
    assert support["sources"] == ["opendart"]

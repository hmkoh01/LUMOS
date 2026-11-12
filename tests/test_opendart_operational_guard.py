from src.sources.collectors.base import CollectedItem, SourceQuery
from src.sources.collectors.opendart import OpenDARTCollector
from src.sources.opendart_corporations import CorporationRecord, CorporationResolution


def test_opendart_only_allows_an_explicit_company_match_not_general_economy_or_industry():
    item = CollectedItem(source="opendart", source_item_id="r1", title="Filing", author="Example Semiconductor Corp", url="https://dart.example/r1", metrics_json={"corporation_code": "00123456"})
    assert OpenDARTCollector._matches(item, {"company_name": "Example Semiconductor Corp", "corp_code": "00123456"})
    assert not OpenDARTCollector._matches(item, {"raw_interest": "semiconductor industry", "corp_code": "00123456"})
    assert not OpenDARTCollector._matches(item, {"company_name": "Example Semiconductor Corp", "corp_code": "00999999"})
    assert not OpenDARTCollector._matches(item, {})


def test_verified_stock_code_alias_is_allowed_only_when_the_cache_returns_one_official_company(monkeypatch):
    monkeypatch.setenv("OPENDART_API_KEY", "fixture")

    class Directory:
        def resolve(self, _name):
            return CorporationResolution("not_found")

        def resolve_stock_code(self, code):
            assert code == "000660"
            return CorporationResolution("resolved", CorporationRecord("00123456", "Official Company", "000660"))

    payload = {"status": "000", "list": [{
        "rcept_no": "20261110000001", "report_nm": "Filing", "rcept_dt": "20261110",
        "corp_code": "00123456", "corp_name": "Official Company",
    }]}
    result = OpenDARTCollector(fetch_json=lambda *_: payload, corporation_cache=Directory()).collect([
        SourceQuery(source="opendart", query="User Alias", params={
            "company_name": "User Alias", "verified_stock_code": "000660", "bgn_de": "20261109", "end_de": "20261110",
        })
    ], limit=10)
    assert len(result.items) == 1


def test_opendart_official_013_is_a_normal_empty_company_result(monkeypatch):
    monkeypatch.setenv("OPENDART_API_KEY", "fixture")

    class Directory:
        def resolve(self, _name):
            return CorporationResolution("resolved", CorporationRecord("00123456", "Example Corp", "123456"))

    result = OpenDARTCollector(fetch_json=lambda *_: {"status": "013", "message": "not retained"}, corporation_cache=Directory()).collect([
        SourceQuery(source="opendart", query="Example Corp", params={"company_name": "Example Corp", "bgn_de": "20261109", "end_de": "20261110"})
    ], limit=10)
    assert result.errors == []
    assert result.items == []
    assert result.warnings == ["opendart_no_data"]

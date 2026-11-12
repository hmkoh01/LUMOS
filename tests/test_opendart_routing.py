from src.sources.router import ROUTE_INFORMATION_TYPES, ROUTING_RULES, SourceRouter


def test_company_tracking_can_select_opendart_without_making_it_general_economy_news():
    configs = [{"source_id": "opendart", "selection_mode": "auto", "enabled": True, "priority": 90, "config_json": {}}]
    # Registry permission review keeps the source out of a live plan today.
    routes = SourceRouter().plan({}, {}, [], [{"keyword": "Samsung company", "category": "COMPANY_TRACKING", "status": "active"}], source_configs=configs)
    assert routes == []
    assert "opendart" in ROUTING_RULES["COMPANY_TRACKING"]
    assert "disclosure" in ROUTE_INFORMATION_TYPES["COMPANY_TRACKING"]

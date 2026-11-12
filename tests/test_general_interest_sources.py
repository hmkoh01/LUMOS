import os
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from src.engine.collection.source_support import collection_support
from src.sources.collectors.base import SourceQuery
from src.sources.collectors.crossref import CrossrefCollector
from src.sources.collectors.rss import RSSCollector
from src.sources.query_planner import QueryPlanner
from src.sources.router import SourceRouter
from src.sources.source_registry import OFFICIAL_AI_TREND_FEEDS, source_availability


def test_specialised_interest_never_falls_back_to_tech_pilot_sources():
    # "startup" has a product hint too, but a grant must wait for the official
    # program source rather than becoming a Hacker News recommendation.
    support = collection_support("startup grant", ("github", "hackernews"))
    assert support["status"] == "awaiting_approved_source"
    assert support["sources"] == []

    for interest in ("stock market", "youth policy", "travel festival", "career hiring", "research paper"):
        assert collection_support(interest, ("github", "hackernews"))["sources"] == []


def test_research_waits_for_a_discovery_source_even_when_crossref_is_configured():
    support = collection_support("research paper", ("crossref",))
    # OpenAlex is a route candidate but remains disabled until an operator
    # records the zero-cost metadata-only operating policy.
    assert support["status"] == "awaiting_approved_source"
    assert "crossref" not in support["source_states"]

    with patch.dict(os.environ, {"CROSSREF_MAILTO": "lumos-test@example.com"}, clear=False):
        ready = collection_support("research paper", ("crossref",))
    assert ready["status"] == "awaiting_approved_source"
    assert ready["sources"] == []


def test_openalex_requires_an_approved_policy_and_a_free_api_key_before_live_availability():
    config = {"usage_status": "approved"}
    with patch.dict(os.environ, {"OPENALEX_API_KEY": ""}, clear=False):
        assert source_availability("openalex", config)["state"] == "configuration_required"
    with patch.dict(os.environ, {"OPENALEX_API_KEY": "test-free-key"}, clear=False):
        assert source_availability("openalex", config)["available"]


def test_rss_cannot_become_supported_before_source_rights_are_recorded():
    feed = {"feed_urls": ["https://example.test/feed"]}
    assert source_availability("rss", feed)["state"] == "permission_review"
    assert source_availability("rss", {**feed, "usage_status": "approved"})["available"]


def test_crossref_is_not_an_automatic_research_discovery_route_when_configured():
    configs = [{
        "source_id": "crossref", "selection_mode": "auto", "priority": 70,
        "config_json": {"collector": "crossref", "content_type": "research_metadata"},
    }]
    with patch.dict(os.environ, {"CROSSREF_MAILTO": "lumos-test@example.com"}, clear=False):
        routes = SourceRouter().plan({}, {}, [], [{"keyword": "research paper", "status": "active"}], source_configs=configs)
    assert routes == []


def test_crossref_collector_keeps_metadata_and_does_not_require_full_text():
    payload = {"message": {"items": [{
        "DOI": "10.1000/example", "title": ["A research result"],
        "published-online": {"date-parts": [[2026, 11, 8]]},
        "created": {"date-parts": [[2026, 11, 9]]},
        "indexed": {"date-parts": [[2026, 11, 10]]},
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "is-referenced-by-count": 12, "abstract": "<jats:p>metadata excerpt</jats:p>",
        "type": "journal-article", "publisher": "Example Press",
    }]}}
    collector = CrossrefCollector(fetch_json=lambda _url, _timeout, _headers: payload)
    result = collector.collect([SourceQuery(source="crossref", query="research")], limit=5)
    assert not result.errors
    item = result.item_dicts()[0]
    assert item["url"] == "https://doi.org/10.1000/example"
    assert item["metrics_json"]["content_kind"] == "research_metadata"
    assert item["published_at"].startswith("2026-11-08")
    assert item["metrics_json"]["metadata_created_at"].startswith("2026-11-09")
    assert item["metrics_json"]["metadata_indexed_at"].startswith("2026-11-10")
    assert item["summary"] == ""


def test_crossref_uses_earliest_complete_publication_date_not_later_print_issue():
    record = {
        "DOI": "10.1000/online-first", "title": ["Online first result"],
        "published-online": {"date-parts": [[2025, 3, 4]]},
        "published-print": {"date-parts": [[2026, 1, 1]]},
        "issued": {"date-parts": [[2025, 3, 4]]},
        "created": {"date-parts": [[2026, 1, 2]]},
        "indexed": {"date-parts": [[2026, 1, 3]]},
    }
    item = CrossrefCollector()._normalise(record, SourceQuery(source="crossref", query="research"))
    assert item.published_at.startswith("2025-03-04")
    assert item.metrics_json["publication_date_source"] == "published_online"
    assert item.metrics_json["published_print_at"].startswith("2026-01-01")


def test_crossref_does_not_invent_day_for_year_only_date():
    record = {"DOI": "10.1000/year-only", "title": ["Year-only result"], "published-online": {"date-parts": [[2026]]}}
    item = CrossrefCollector()._normalise(record, SourceQuery(source="crossref", query="research"))
    assert item.published_at is None
    assert item.metrics_json["published_online_precision"] == "year"
    assert item.metrics_json["publication_date_precision"] == "unknown"
    assert item.to_dict()["published_at"] is None


def test_crossref_filters_broad_query_noise_and_rejects_future_publication_dates():
    payload = {"message": {"items": [
        {"DOI": "10.1000/noise", "title": ["Advertising research"], "issued": {"date-parts": [[2025, 1, 1]]}},
        {"DOI": "10.1000/future", "title": ["LLM future work"], "issued": {"date-parts": [[2200, 1, 1]]}},
        {"DOI": "10.1000/keep", "title": ["LLM evaluation"], "issued": {"date-parts": [[2025, 1, 1]]}},
    ]}}
    result = CrossrefCollector(fetch_json=lambda *_args: payload).collect(
        [SourceQuery(source="crossref", query="LLM research paper")], limit=5
    )
    assert [item.source_item_id for item in result.items] == ["10.1000/keep"]


def test_crossref_requires_a_structurally_valid_doi_before_making_a_source_link():
    record = {"DOI": "not-a-doi", "title": ["LLM evaluation"], "issued": {"date-parts": [[2025, 1, 1]]}}
    assert CrossrefCollector()._normalise(record, SourceQuery(source="crossref", query="LLM")) is None


def test_crossref_discovery_request_is_title_scoped_bounded_and_never_empty():
    collector = CrossrefCollector()
    url = collector._url("Large Language Model", 99, "private@example.test", {"crossref_search_field": "query.title"})
    parsed = parse_qs(urlparse(url).query)
    assert parsed["query.title"] == ["Large Language Model"]
    assert parsed["rows"] == ["20"]
    assert parsed["filter"][0].startswith("until-pub-date:")
    assert "sort" not in parsed and "order" not in parsed
    assert parsed["mailto"] == ["private@example.test"]
    try:
        collector._url("   ", 5, "", {})
    except ValueError as exc:
        assert "must not be empty" in str(exc)
    else:
        raise AssertionError("empty Crossref query should not form an all-works request")


def test_crossref_planner_uses_precise_llm_title_query_and_preserves_raw_interest():
    routes = [{"source": "crossref", "category": "RESEARCH", "source_config": {}}]
    planned = QueryPlanner().build_queries(routes, {}, [{"keyword": "LLM research paper", "status": "active"}])
    query = planned[0]["queries"][0]
    assert query["query"] == "Large Language Model"
    assert query["params"]["raw_interest"] == "LLM research paper"
    assert query["params"]["crossref_search_field"] == "query.title"
    assert "foundation model" not in [term.casefold() for term in query["params"]["accepted_title_terms"]]


def test_crossref_reuses_a_short_query_cache_between_collectors():
    calls = []
    CrossrefCollector._cache.clear()
    CrossrefCollector._last_request_at = 0.0
    payload = {"message": {"items": [{"DOI": "10.1000/cache", "title": ["Cached record"]}]}}
    collector = CrossrefCollector(fetch_json=lambda *_args: calls.append(1) or payload)
    query = [SourceQuery(source="crossref", query="cache-test")]
    collector.collect(query, limit=1)
    CrossrefCollector(fetch_json=lambda *_args: calls.append(1) or payload).collect(query, limit=1)
    assert len(calls) == 1


def test_rss_metadata_only_policy_does_not_store_feed_excerpt_or_invent_date():
    xml = """<rss><channel><title>Official source</title><item>
      <title>AI policy update</title><link>https://example.test/item</link>
      <description>Publisher-owned excerpt</description><pubDate>invalid-date</pubDate>
    </item></channel></rss>"""
    result = RSSCollector(fetch_text=lambda *_args: xml).collect([
        SourceQuery(source="rss", query="AI", params={"feed_url": "https://example.test/rss", "content_policy": {"excerpt_storage": "not_approved"}})
    ], limit=1)
    item = result.items[0]
    assert item.summary == ""
    assert item.published_at is None
    assert item.raw_json["content_policy"]["excerpt_storage"] == "not_approved"


def test_rss_honours_declared_encoding_and_dc_date_without_refetching():
    encoded = '<?xml version="1.0" encoding="euc-kr"?><rss />'.encode("euc-kr")
    assert RSSCollector._decode_payload(encoded).startswith("<?xml")
    xml = """<feed xmlns='http://www.w3.org/2005/Atom' xmlns:dc='http://purl.org/dc/elements/1.1/'>
      <title>Official</title><entry><title>AI policy</title><link href='https://example.test/a'/>
      <dc:date>2026-11-08T09:00:00+09:00</dc:date></entry></feed>"""
    item = RSSCollector(fetch_text=lambda *_args: xml).collect(
        [SourceQuery(source="rss", query="", params={"feed_url": "https://example.test/rss"})], 1
    ).items[0]
    assert item.published_at == "2026-11-08T09:00:00"


def test_broad_feed_uses_title_only_type_filter_and_keeps_observation_provenance():
    xml = """<rss><channel><title>Google Blog</title>
      <item><title>Gemini introduces a new AI model</title><link>https://example.test/gemini</link>
      <pubDate>Sat, 08 Nov 2026 09:00:00 +0000</pubDate><description>Publisher excerpt</description></item>
      <item><title>Investing in Wyoming infrastructure</title><link>https://example.test/wyoming</link>
      <pubDate>Sat, 08 Nov 2026 08:00:00 +0000</pubDate></item>
    </channel></rss>"""
    result = RSSCollector(fetch_text=lambda *_args: xml).collect([
        SourceQuery(source="rss", query="https://example.test/rss", category="AI_TREND", params={
            "feed_url": "https://example.test/rss", "keywords": ["ai trend"],
            "source_role": "primary", "verification_status": "official_source",
            "content_filter": {"any_terms": ["ai", "gemini", "model"], "allow_category_match": True},
            "content_policy": {"excerpt_storage": "not_approved"},
        })
    ], 5)
    assert [item.title for item in result.items] == ["Gemini introduces a new AI model"]
    item = result.items[0]
    assert item.summary == ""
    assert item.raw_json["source_role"] == "primary"
    assert item.raw_json["verification_status"] == "official_source"
    assert item.raw_json["source_published_at"] == item.published_at
    assert item.raw_json["first_observed_at"] == item.collected_at


def test_msit_rss_entries_remain_permission_review_and_record_scope():
    for source_id in ("msit_business_rss", "msit_recruitment_rss"):
        assert source_availability(source_id, {"feed_urls": ["https://example.test/rss"]})["state"] == "permission_review"
        policy = OFFICIAL_AI_TREND_FEEDS[source_id]
        assert policy["metadata_storage"] == "allowed_for_validation_only"
        assert policy["ai_summary"] == "per_item_license_required"

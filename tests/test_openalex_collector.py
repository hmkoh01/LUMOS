from urllib.parse import parse_qs, urlparse

from datetime import date
from unittest.mock import patch

from src.engine.config import EngineConfig
from src.engine.evaluation.scorer import evaluate_candidates
from src.engine.models import Period, RawCandidate
from src.sources.collectors.base import SourceQuery
from src.sources.collectors.openalex import OpenAlexCollector
from src.sources.query_planner import QueryPlanner


def _work(title="Large Language Model evaluation", date="2026-10-01", updated="2026-11-08", doi="https://doi.org/10.1000/test"):
    return {
        "id": "https://openalex.org/W123", "title": title, "publication_date": date, "updated_date": updated,
        "doi": doi, "type": "article", "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
        "topics": [{"topic": {"display_name": "Natural language processing"}}],
        "primary_location": {"landing_page_url": "https://example.test/work"},
    }


def test_openalex_request_is_one_bounded_metadata_only_search():
    collector = OpenAlexCollector()
    url = collector._url("Large Language Model", 99, {"reference_date": "2026-11-08"})
    parsed = parse_qs(urlparse(url).query)
    assert parsed["per-page"] == ["20"]
    assert parsed["search.title_abstract_keywords"] == ["Large Language Model"]
    assert "search" not in parsed
    assert parsed["sort"] == ["relevance_score:desc,publication_date:desc"]
    assert parsed["filter"] == ["from_publication_date:2026-10-10,type:article"]
    assert "updated_date" in parsed["select"][0]
    assert "abstract" not in parsed["select"][0]


def test_openalex_monthly_shared_search_uses_kst_calendar_window():
    collector = OpenAlexCollector()
    shared = parse_qs(urlparse(collector._url("LLM", 20, {"briefing_period": "monthly", "reference_date": "2026-11-08"})).query)["filter"][0]
    assert "from_publication_date:2026-10-10" in shared
    # A KST date transition is explicit and does not borrow UTC's previous day.
    transition = parse_qs(urlparse(collector._url("LLM", 20, {"reference_date": "2026-01-01"})).query)["filter"][0]
    assert "from_publication_date:2025-12-03" in transition


def test_query_planner_makes_one_monthly_shared_query_per_research_interest():
    planned = QueryPlanner().build_queries(
        [{"source": "openalex", "category": "RESEARCH", "source_config": {}}], {},
        [{"keyword": "LLM research paper", "status": "active"}],
    )
    queries = planned[0]["queries"]
    assert len(queries) == 1
    assert queries[0]["params"]["briefing_period"] == "monthly"
    assert queries[0]["params"]["collection_scope"] == "monthly_shared"


def test_openalex_reports_provider_budget_headers_without_storing_them_in_items():
    collector = OpenAlexCollector(fetch_json=lambda *_args: ({"meta": {"cost_usd": 0.0}, "results": [_work()]}, {
        "x-ratelimit-remaining": "99", "x-ratelimit-reset": "123",
    }))
    result = collector.collect([SourceQuery(source="openalex", query="Large Language Model")], 1)
    assert "openalex_cost_usd=0.0" in result.warnings
    assert "openalex_rate_limit_remaining=99" in result.warnings


def test_openalex_sends_a_configured_free_key_only_as_an_authorization_header():
    captured = {}
    OpenAlexCollector._cache.clear()
    collector = OpenAlexCollector(fetch_json=lambda url, _timeout, headers: captured.update(url=url, headers=headers) or {"results": [_work()]})
    with patch.dict("os.environ", {"OPENALEX_API_KEY": "private-test-key"}, clear=False):
        collector.collect([SourceQuery(source="openalex", query="Large Language Model")], 1)
    assert captured["headers"]["Authorization"] == "Bearer private-test-key"
    assert "private-test-key" not in captured["url"]


def test_openalex_keeps_publication_and_metadata_dates_separate_and_filters_future_noise():
    payload = {"results": [
        _work(), _work(title="Large Language Model future", date="2200-01-01", doi="https://doi.org/10.1000/future"),
        _work(title="Advertising research", doi="https://doi.org/10.1000/noise"),
    ]}
    result = OpenAlexCollector(fetch_json=lambda *_args: payload).collect(
        [SourceQuery(source="openalex", query="Large Language Model", params={"raw_interest": "LLM research paper"})], 5
    )
    assert len(result.items) == 1
    item = result.items[0]
    assert item.published_at.startswith("2026-10-01")
    assert item.metrics_json["metadata_updated_at"].startswith("2026-11-08")
    assert item.metrics_json["publication_date_precision"] == "day"
    assert item.metrics_json["research_role"] == "research_update"
    assert item.summary == ""
    assert item.raw_json["fulltext_collected"] is False


def test_openalex_marks_surveys_as_reference_material_without_changing_publication_date():
    item = OpenAlexCollector()._normalise(
        _work(title="A Survey of Large Language Models"),
        SourceQuery(source="openalex", query="Large Language Model", params={"raw_interest": "LLM research paper"}),
    )
    assert item.metrics_json["research_role"] == "reference_review"
    assert item.published_at.startswith("2026-10-01")


def test_openalex_cache_prevents_a_second_external_fetch():
    calls = []
    OpenAlexCollector._cache.clear()
    collector = OpenAlexCollector(fetch_json=lambda *_args: calls.append(1) or {"results": [_work()]})
    query = [SourceQuery(source="openalex", query="Large Language Model")]
    collector.collect(query, 5)
    collector.collect(query, 5)
    assert len(calls) == 1


def test_day_precision_makes_old_research_ineligible_for_current_briefing_periods():
    candidate = RawCandidate(
        dedupe_key="old-research", title="A Survey of Large Language Models",
        published_at="2026-05-09T00:00:00", metrics={
            "content_kind": "research_metadata", "publication_date_precision": "day",
            "research_role": "reference_review",
        },
    )
    for period in (Period.DAILY, Period.WEEKLY, Period.MONTHLY):
        assert evaluate_candidates([candidate], period, ["LLM"], EngineConfig(), reference_date=date(2026, 11, 8)) == []

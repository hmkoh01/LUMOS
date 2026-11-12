from unittest.mock import patch

from src.sources.router import SourceRouter
from src.sources.source_registry import SOURCE_CAPABILITIES
from src.sources.source_registry import OFFICIAL_AI_TREND_FEEDS


def _config(source_id, config_json=None, priority=50):
    return {
        "source_id": source_id,
        "selection_mode": "auto",
        "enabled": True,
        "priority": priority,
        "config_json": config_json or {},
    }


def _approved_news_configs():
    approved_feed = {"usage_status": "approved", "feed_urls": ["https://example.test/feed.xml"]}
    return [
        _config("official_ai_blogs", approved_feed, 90),
        _config("company_newsroom", approved_feed, 80),
        _config("rss", approved_feed, 70),
        _config("github", {"min_stars": 20}, 75),
        _config("hackernews", {}, 80),
    ]


def _sources_for(interest, configs=None):
    routes = SourceRouter().plan({}, {}, [], [{"keyword": interest, "status": "active"}], source_configs=configs or _approved_news_configs())
    return [route["source"] for route in routes], routes


def test_ai_trend_uses_approved_news_sources_not_github_or_hackernews():
    sources, routes = _sources_for("AI trend")
    assert sources == ["official_ai_blogs", "company_newsroom", "rss"]
    assert all("github" != source and "hackernews" != source for source in sources)
    assert all(route["category"] == "AI_TREND" for route in routes)


def test_ai_open_source_routes_to_code_sources_not_general_ai_news_sources():
    sources, routes = _sources_for("AI open source")
    assert "github" in sources
    assert "official_ai_blogs" not in sources
    assert all(route["category"] == "AI_OPEN_SOURCE" for route in routes)


def test_llm_research_does_not_fall_back_to_crossref_or_tech_sources_when_arxiv_is_not_ready():
    with patch.dict("os.environ", {"CROSSREF_MAILTO": "test@example.test"}, clear=False):
        sources, routes = _sources_for("LLM research paper")
    assert sources == []
    assert routes == []


def test_specialised_interest_categories_do_not_route_to_low_relevance_pilot_sources():
    for interest in (
        "startup support program",
        "junior developer hiring",
        "youth housing",
    ):
        sources, _routes = _sources_for(interest)
        assert sources == []


def test_msit_rss_routes_only_when_an_operator_records_reuse_approval():
    configs = [
        _config("msit_business_rss", {
            "usage_status": "approved", "feed_urls": ["https://example.test/business"],
            "content_type": "startup_program",
        }),
        _config("msit_recruitment_rss", {
            "usage_status": "approved", "feed_urls": ["https://example.test/jobs"],
            "content_type": "career",
        }),
    ]
    startup_sources, startup_routes = _sources_for("startup support program", configs)
    career_sources, career_routes = _sources_for("junior developer hiring", configs)
    assert startup_sources == ["msit_business_rss"]
    assert startup_routes[0]["category"] == "STARTUP_PROGRAM"
    assert career_sources == ["msit_recruitment_rss"]
    assert career_routes[0]["category"] == "CAREER"


def test_semiconductor_industry_routes_to_industry_news_and_excludes_github():
    sources, routes = _sources_for("semiconductor industry trend")
    assert sources == ["company_newsroom", "rss"]
    assert "github" not in sources
    assert all(route["category"] == "SEMICONDUCTOR_INDUSTRY" for route in routes)


def test_source_can_be_excluded_or_preferred_for_a_specific_interest_type():
    configs = _approved_news_configs()
    for config in configs:
        if config["source_id"] == "rss":
            config["config_json"] = {**config["config_json"], "excluded_for": ["AI_TREND"]}
        if config["source_id"] == "company_newsroom":
            config["config_json"] = {**config["config_json"], "preferred_for": ["AI_TREND"]}
    sources, routes = _sources_for("AI trend", configs)
    assert sources == ["company_newsroom", "official_ai_blogs"]
    assert routes[0]["source"] == "company_newsroom"


def test_source_capabilities_distinguish_code_metadata_and_newsletter_readiness():
    assert SOURCE_CAPABILITIES["github"]["source_kind"] == "code_repository"
    assert SOURCE_CAPABILITIES["github"]["news_capable"] is False
    assert SOURCE_CAPABILITIES["crossref"]["source_kind"] == "bibliographic_metadata"
    assert SOURCE_CAPABILITIES["crossref"]["news_capable"] is False
    assert SOURCE_CAPABILITIES["official_ai_blogs"]["news_capable"] is True


def test_official_ai_feed_policy_records_evidence_and_does_not_auto_approve_private_newsrooms():
    assert OFFICIAL_AI_TREND_FEEDS["msit_press"]["metadata_storage"] == "allowed_for_validation"
    assert OFFICIAL_AI_TREND_FEEDS["openai_news"]["activation_state"] == "permission_review"
    assert OFFICIAL_AI_TREND_FEEDS["google_blog"]["ai_summary"] == "not_granted"

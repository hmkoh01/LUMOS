from src.sources.content_rights import (
    assess_kogl_page, classify_opportunity_status, decode_rights_document,
    extract_msit_published_at, item_allows_delivery, item_allows_llm,
)
from src.signals.llm_briefing import _source_allowed
from src.sources.collectors.base import SourceQuery
from src.sources.collectors.rss import RSSCollector


def test_kogl_type_one_allows_commercial_derivative_summary_with_attribution():
    decision = assess_kogl_page(
        "<img alt='\\uacf5\\uacf5\\ub204\\ub9ac \\uc81c1\\uc720\\ud615'><img alt='\\uc778\\uacf5\\uc9c0\\ub2a5 \\ud559\\uc2b5 \\uac00\\ub2a5 AI \\uc720\\ud615'>".encode().decode("unicode_escape"),
        evidence_url="https://example.test/post", publisher="Example Ministry",
        title="AI support announcement", published_at="2026-11-08T09:00:00",
    )
    assert decision["license_type"] == 1
    assert decision["ai_training_scope"] == "training_data_only"
    assert decision["ai_summary"] == "allowed_with_attribution"
    assert decision["recommendation_eligible"] is True
    assert "Example Ministry" in decision["attribution_text"]
    item = {"raw_json": {"requires_post_rights": True, "content_rights": decision}}
    assert item_allows_llm(item)
    assert item_allows_delivery(item)


def test_ai_training_mark_without_a_kogl_type_never_becomes_summary_permission():
    decision = assess_kogl_page(
        "<span>\\uc778\\uacf5\\uc9c0\\ub2a5 \\ud559\\uc2b5 \\uac00\\ub2a5 AI \\uc720\\ud615</span>".encode().decode("unicode_escape"),
        evidence_url="https://example.test/post", publisher="Example Ministry", title="Notice",
    )
    assert decision["ai_training_marked"] is True
    assert decision["ai_training_scope"] == "training_data_only"
    assert decision["recommendation_eligible"] is False
    assert decision["ai_summary"] == "not_allowed"


def test_restricted_or_missing_type_is_metadata_link_only():
    decision = assess_kogl_page(
        "\\uacf5\\uacf5\\ub204\\ub9ac \\uc81c3\\uc720\\ud615".encode().decode("unicode_escape"),
        evidence_url="https://example.test/post", publisher="Example Ministry", title="Notice",
    )
    item = {"raw_json": {"requires_post_rights": True, "content_rights": decision}}
    assert decision["recommendation_eligible"] is False
    assert not item_allows_llm(item)
    assert not item_allows_delivery(item)


def test_rights_page_decoder_preserves_cp949_kogl_alt_text():
    html = "<img alt='\\uacf5\\uacf5\\ub204\\ub9ac \\uc81c1\\uc720\\ud615'>".encode().decode("unicode_escape")
    decoded = decode_rights_document(html.encode("cp949"), "text/html; charset=EUC-KR")
    decision = assess_kogl_page(decoded, evidence_url="https://example.test/post", publisher="Ministry", title="Notice")
    assert decision["license_type"] == 1


def test_msit_open_mark_fixture_ignores_footer_and_separates_ai_training():
    u = lambda value: value.encode().decode("unicode_escape")
    html = u("""
      <article><div class='open_mark'><img alt='open \\uacf5\\uacf5\\ub204\\ub9ac'><strong>\\uc81c1\\uc720\\ud615 : \\ucd9c\\ucc98\\ud45c\\uc2dc</strong></div>
      <div class='open_mark'><img alt='open \\uacf5\\uacf5\\ub204\\ub9ac \\uc778\\uacf5\\uc9c0\\ub2a5 \\ud559\\uc2b5 \\uac00\\ub2a5'><strong>AI \\uc720\\ud615</strong></div></article>
      <footer>\\uacf5\\uacf5\\ub204\\ub9ac \\uc81c4\\uc720\\ud615 \\uc77c\\ubc18 \\uc548\\ub0b4</footer>
    """)
    decision = assess_kogl_page(html, evidence_url="https://example.test/post", publisher="MSIT", title="Notice")
    assert decision["license_type"] == 1
    assert decision["ai_training_marked"] is True
    assert decision["recommendation_eligible"] is True


def test_msit_publication_date_needs_a_publication_label_not_a_revision_or_filename():
    u = lambda value: value.encode().decode("unicode_escape")
    assert extract_msit_published_at(u("<dl><dt>\\ub4f1\\ub85d\\uc77c</dt><dd>2026. 11. 08.</dd></dl>")) == "2026-11-08"
    assert extract_msit_published_at(u("<p>\\uc218\\uc815\\uc77c 2026. 11. 08.</p><a>260101 \\ubcf4\\ub3c4\\uc790\\ub8cc.hwp</a>")) is None


def test_result_and_interview_notices_are_not_fresh_opportunities():
    u = lambda value: value.encode().decode("unicode_escape")
    assert classify_opportunity_status(u("\\uc11c\\ub958\\uc804\\ud615 \\ud569\\uaca9\\uc790 \\ubc0f \\uba74\\uc811\\uc77c\\uc815 \\uacf5\\uace0")) == "not_new_opportunity"
    assert classify_opportunity_status(u("\\uc804\\ubb38\\uc784\\uae30\\uc81c \\ucc44\\uc6a9 \\ubaa8\\uc9d1 \\uacf5\\uace0")) == "unknown"


def test_item_rights_gate_blocks_pending_rss_but_preserves_existing_source_path():
    pending = {"raw_json": {"requires_post_rights": True}}
    eligible = {"raw_json": {"requires_post_rights": True, "content_rights": {
        "recommendation_eligible": True,
        "llm_input": "allowed_for_inference_with_attribution_and_provider_review",
        "user_delivery": "allowed_with_attribution",
    }}}
    assert not _source_allowed("msit_press_validation", pending)
    assert _source_allowed("msit_press_validation", eligible)
    assert _source_allowed("github", {"raw_json": {}})


def test_opportunity_only_feed_omits_selection_and_interview_notices():
    u = lambda value: value.encode().decode("unicode_escape")
    xml = u("""<rss><channel><title>MSIT</title>
      <item><title>\\uc120\\uc815\\uacb0\\uacfc \\uacf5\\uace0</title><link>https://example.test/result</link></item>
      <item><title>\\uc2e0\\uaddc \\ucc44\\uc6a9 \\ubaa8\\uc9d1 \\uacf5\\uace0</title><link>https://example.test/open</link></item>
    </channel></rss>""")
    result = RSSCollector(fetch_text=lambda *_: xml).collect([SourceQuery(
        source="rss", query="", params={"feed_url": "https://example.test/rss", "opportunity_only": True}
    )], 5)
    assert [item.url for item in result.items] == ["https://example.test/open"]

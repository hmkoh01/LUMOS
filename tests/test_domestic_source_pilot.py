import unittest
from unittest.mock import patch

from src.signals.korean_briefing import build_korean_briefing
from src.sources.collectors.base import SourceQuery
from src.sources.collectors.rss import RSSCollector
from src.sources.query_planner import QueryPlanner
from src.sources.router import SourceRouter
from src.sources.source_registry import source_availability


ATOM_FIXTURE = """<?xml version='1.0' encoding='utf-8'?>
<feed xmlns='http://www.w3.org/2005/Atom'>
  <title>GeekNews</title>
  <entry><title>한국 보안 연구 보고서</title><link href='https://example.test/report?utm_source=rss'/>
  <summary>개인정보 보호와 보안 대응을 다룬 보고서입니다.</summary>
  <updated>2026-10-16T09:30:00+09:00</updated></entry>
  <entry><title>한국 보안 연구 보고서</title><link href='https://example.test/report?utm_source=rss'/>
  <summary>중복 항목</summary><updated>2026-10-16T09:30:00+09:00</updated></entry>
</feed>"""


class DomesticSourcePilotTest(unittest.TestCase):
    def test_atom_fixture_keeps_publication_metadata_and_deduplicates(self):
        collector = RSSCollector(fetch_text=lambda _url, _timeout: ATOM_FIXTURE, source_id="geeknews")
        query = SourceQuery(
            source="geeknews", query="", params={
                "feed_urls": ["https://news.hada.io/rss/news"], "language": "ko",
                "source_region": "domestic", "content_type": "community",
                "usage_status": "permission_review",
            },
        )
        result = collector.collect([query], limit=10)
        self.assertEqual(len(result.items), 1)
        item = result.item_dicts()[0]
        self.assertEqual(item["published_at"], "2026-10-16T09:30:00")
        self.assertEqual(item["raw_json"]["language"], "ko")
        self.assertEqual(item["raw_json"]["source_region"], "domestic")
        self.assertEqual(item["raw_json"]["event_occurred_at"], None)

    def test_permission_review_sources_are_never_collectable(self):
        for source_id in ("geeknews", "kisa_press", "kisa_research"):
            status = source_availability(source_id, {"feed_urls": ["https://example.test/feed"]})
            self.assertFalse(status["available"])
            self.assertIn("이용 조건", status["reason"])

    def test_korean_text_skips_translation_but_still_builds_briefing(self):
        with patch("src.signals.korean_briefing.translate_to_korean") as translate:
            briefing = build_korean_briefing(
                "개인정보 보호 연구 보고서", "국내 개인정보 보호 현황을 조사한 보고서입니다.",
                source="kisa_research", category="SECURITY_PRIVACY", matched_keywords=["개인정보 보호"],
            )
        translate.assert_not_called()
        self.assertEqual(briefing["original_language"], "ko")
        self.assertIn("개인정보", briefing["display_summary_ko"])

    def test_permission_review_domestic_sources_do_not_enter_routes(self):
        configs = [
            {"source_id": "geeknews", "selection_mode": "enabled", "config_json": {"feed_urls": ["https://news.hada.io/rss/news"]}},
            {"source_id": "kisa_press", "selection_mode": "auto", "config_json": {"feed_urls": ["https://kisa.or.kr/rss/402"]}},
        ]
        routes = SourceRouter().plan({}, {"source_region_preference": "domestic"}, [], [{"keyword": "정보보안", "status": "active"}], source_configs=configs)
        self.assertNotIn("geeknews", {route["source"] for route in routes})
        self.assertNotIn("kisa_press", {route["source"] for route in routes})

    def test_query_planner_preserves_rss_source_context(self):
        route = {"source": "kisa_research", "category": "SECURITY_PRIVACY", "source_config": {
            "feed_urls": ["https://kisa.or.kr/rss/201"], "language": "ko", "source_region": "domestic",
            "content_type": "research_report", "usage_status": "permission_review",
        }}
        planned = QueryPlanner().build_queries([route], {}, [{"keyword": "정보보안", "status": "active"}])
        self.assertEqual(planned[0]["queries"][0]["params"]["content_type"], "research_report")


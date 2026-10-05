import tempfile
import unittest
import time
from urllib.parse import urlsplit, parse_qs
from pathlib import Path

from src.context.interest_matching import matches_interest
from src.signals.candidate import CandidateBuilder
from src.signals.generator import SignalGenerator
from src.signals.ranking import RankingService
from src.sources.query_planner import QueryPlanner
from src.sources.collectors.base import SourceQuery
from src.sources.collectors.hackernews import HackerNewsCollector
from src.sources.collectors.rss import RSSCollector
from src.signals.commercial_filter import commercial_page_reason, commercial_context_reason
from src.signals.candidate import is_youtube_short
from src.storage.sqlite_store import SQLiteStore


class SignalRelevanceTest(unittest.TestCase):
    def test_bilingual_matching_and_word_boundaries(self):
        self.assertTrue(matches_interest("New marketing tools", "마케팅"))
        self.assertFalse(matches_interest("Agricultural marketing for farmers", "마케팅"))
        self.assertTrue(matches_interest("A content-strategy guide", "콘텐츠 기획자"))
        self.assertTrue(matches_interest("마케팅을 위한 도구", "마케팅"))
        self.assertFalse(matches_interest("Retail said profits rose", "AI"))
        self.assertFalse(matches_interest("Doctor discusses surgery", "마케팅"))
        self.assertFalse(matches_interest("Random news", "알 수 없는 관심사"))
        self.assertTrue(matches_interest("Better analytics for marketing teams", "데이터마케터"))
        self.assertTrue(matches_interest("Marketing attribution tools", "데이터 마케터"))
        self.assertTrue(matches_interest("Content strategy guide", "콘텐츠기획에 관심이 있어요"))
        self.assertFalse(matches_interest("A data storage engine", "데이터 마케터"))
        self.assertFalse(matches_interest("content " + "unrelated " * 20 + "strategy", "콘텐츠 기획자"))

    def test_search_finds_interest_outside_popular_stories(self):
        requests = []
        def fetch(url, timeout):
            requests.append(url)
            return {"hits": [
                {"objectID": "123", "title": "Analytics for marketing teams", "url": "https://example.org/analytics", "created_at_i": int(time.time()), "points": 50},
                {"objectID": "456", "title": "Unrelated database", "url": "https://example.org/database", "created_at_i": int(time.time())},
                {"objectID": "789", "title": "A new tool", "story_text": "intro " * 100 + "marketing analytics", "url": "https://example.org/tool", "created_at_i": int(time.time())},
            ]}
        result = HackerNewsCollector(fetch_json=fetch).collect([SourceQuery(source="hackernews", query="marketing analytics", params={"search": True})], 5)
        self.assertEqual(len(result.items), 2)
        self.assertEqual(parse_qs(urlsplit(requests[0]).query)["query"], ["marketing analytics"])
        self.assertIn("search_by_date", requests[0])
        matched = CandidateBuilder(None).match_keywords(result.item_dicts()[1], ["데이터 마케터"])
        self.assertEqual(matched, ["데이터 마케터"])

    def test_search_failure_does_not_fall_back_to_unrelated_items(self):
        def fail(url, timeout):
            raise RuntimeError("network error")
        result = HackerNewsCollector(fetch_json=fail).collect([SourceQuery(source="hackernews", query="marketing", params={"search": True})], 3)
        self.assertEqual(result.items, [])
        self.assertTrue(result.errors)

    def test_search_shares_collection_limit_between_interest_queries(self):
        def fetch(url, timeout):
            query = parse_qs(urlsplit(url).query)["query"][0]
            return {"hits": [
                {"objectID": f"{query}-{index}", "title": f"{query} update {index}",
                 "url": f"https://example.org/{query}/{index}", "created_at_i": int(time.time())}
                for index in range(5)
            ]}
        queries = [
            SourceQuery(source="hackernews", query="marketing", params={"search": True}),
            SourceQuery(source="hackernews", query="security", params={"search": True}),
        ]
        result = HackerNewsCollector(fetch_json=fetch).collect(queries, 4)
        self.assertEqual(len(result.items), 4)
        self.assertEqual({item.raw_json["search_query"] for item in result.items}, {"marketing", "security"})

    def test_planner_uses_current_interests_in_both_languages(self):
        planner = QueryPlanner()
        keywords = planner._keywords({"role": "doctor", "interest_types_json": ["old topic"]}, [{"keyword": "콘텐츠 기획자"}, {"keyword": "마케팅"}])
        queries = planner._queries_for_source("hackernews", keywords, "", [], "")
        self.assertIn("marketing", [query["query"] for query in queries])
        self.assertNotIn("doctor", keywords)
        self.assertEqual(planner._keywords({}, []), [])

    def test_planner_gives_each_interest_a_query_before_aliases(self):
        queries = QueryPlanner()._queries_for_source(
            "hackernews", ["marketing", "data analysis automation", "AI infrastructure"], "", [], ""
        )
        values = [entry["query"] for entry in queries]
        self.assertEqual(values[:3], ["marketing", "data analysis automation", "ai infrastructure"])

    def test_youtube_uses_intent_phrase_instead_of_a_bare_translation(self):
        queries = QueryPlanner()._queries_for_source("youtube", ["마케팅"], "", [], "CONTENT_SNS")
        self.assertEqual([entry["query"] for entry in queries], ["마케팅 전략", "digital marketing strategy"])
        self.assertEqual([entry["params"]["language"] for entry in queries], ["ko", "en"])
        self.assertIn("farmer", queries[0]["params"]["semantic_excludes"])

    def test_rss_keeps_korean_and_english_interest_terms_for_configured_feeds(self):
        queries = QueryPlanner()._queries_for_source(
            "rss", ["마케팅"], "", [], "CONTENT_SNS", {"feed_urls": ["https://example.org/feed"]}
        )
        self.assertIn("마케팅", queries[0]["params"]["keywords"])
        self.assertIn("marketing", queries[0]["params"]["keywords"])

    def test_unrelated_popular_items_do_not_fill_collector_results(self):
        def fetch(url, timeout):
            return [1] if url.endswith("topstories.json") else {"id": 1, "title": "Doctor discusses surgery", "type": "story", "url": "https://example.org/doctor"}
        queries = [SourceQuery(source="hackernews", query="마케팅")]
        self.assertEqual(HackerNewsCollector(fetch_json=fetch).collect(queries, 3).items, [])
        xml = '<rss><channel><item><title>Doctor discusses surgery</title><link>https://example.org/doctor</link></item><item><title>Marketing strategy</title><link>https://example.org/marketing</link></item></channel></rss>'
        queries = [SourceQuery(source="rss", query="마케팅", params={"feed_urls": ["https://example.org/feed"]})]
        result = RSSCollector(fetch_text=lambda url, timeout: xml).collect(queries, 3)
        self.assertEqual([item.title for item in result.items], ["Marketing strategy"])

    def test_generation_deduplicates_routes_sources_and_tracking_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "test.db")
            store.upsert_interest("마케팅", "onboarding", 1, "onboarding", {})
            rows = []
            for index, (url, title) in enumerate([
                ("https://example.org/article?utm_source=hn", "Marketing strategy"),
                ("http://www.example.org/article/#section", "Marketing strategy"),
                ("https://example.org/other", "Marketing research"),
                ("https://example.org/doctor", "Doctor discusses surgery"),
            ]):
                item_id = store.upsert_source_item({"source": "rss", "source_item_id": str(index), "url": url, "title": title})
                rows.append(store.get_source_item(item_id))
            candidates = CandidateBuilder(store).create_from_source_items(rows + rows, store.get_interests())
            self.assertEqual(len(candidates), 2)
            ranked = RankingService(store).rank(candidates)
            signals = SignalGenerator(store).generate_from_candidates([ranked[0], ranked[0], ranked[1]])
            self.assertEqual(len(signals), 2)
            self.assertEqual(len({signal["source_url"] for signal in signals}), 2)
            self.assertEqual(CandidateBuilder(store).create_from_source_items(rows, []), [])

    def test_generation_fills_requested_count_after_interest_diversity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "test.db")
            store.update_settings({"signal_count": 3})
            store.upsert_interest("마케팅", "test", 1, "manual", {})
            store.upsert_interest("AI", "test", 1, "manual", {})
            candidates = [
                {"title": f"Marketing analysis {index}", "summary": "", "source": "mock",
                 "source_item_id": str(index), "url": f"https://example.com/{index}",
                 "matched_keywords_json": ["마케팅"], "raw_json": {"mock": True}}
                for index in range(3)
            ]
            signals = SignalGenerator(store).generate_from_candidates(candidates)
            self.assertEqual(len(signals), 3)

    def test_commercial_subscription_pages_are_excluded_but_product_news_is_kept(self):
        subscription = {
            "source": "rss", "url": "https://ai.example.com/pricing", "title": "AI service pricing plans",
            "summary": "Start free trial and choose your plan today.",
        }
        product_news = {
            "source": "rss", "url": "https://news.example.com/ai-service-launch", "title": "AI service launches new plan",
            "summary": "The company announced a new subscription option for teams.",
        }
        self.assertEqual(commercial_page_reason(subscription), "commercial_url")
        self.assertEqual(commercial_page_reason(product_news), "")

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "test.db")
            store.upsert_interest("AI", "test", 1, "manual", {})
            rows = []
            for index, item in enumerate((subscription, product_news)):
                item_id = store.upsert_source_item({**item, "source_item_id": str(index)})
                rows.append(store.get_source_item(item_id))
            candidates = CandidateBuilder(store).create_from_source_items(rows, store.get_interests())
            self.assertEqual([candidate["title"] for candidate in candidates], [product_news["title"]])

    def test_commercial_landing_content_is_excluded_after_fetch(self):
        item = {"source": "rss", "url": "https://arda.example", "title": "Arda marketing agents", "summary": ""}
        context = {"status": "available", "title": "Arda", "description": "Simple, transparent pricing for marketing agents.",
                   "text": "Starter is $99/month. Enterprise plans include annual billing. Book a call to get started."}
        self.assertEqual(commercial_context_reason(item, context), "commercial_page_content")

    def test_show_hn_external_homepage_is_not_treated_as_an_article(self):
        item = {"source": "hackernews", "url": "https://spendict.example/",
                "title": "Show HN: Spendict – a performance marketer's verdict for AI agents"}
        self.assertEqual(commercial_page_reason(item), "commercial_show_hn_landing")

    def test_youtube_shorts_link_from_another_source_is_excluded(self):
        self.assertTrue(is_youtube_short({"source": "hackernews", "url": "https://www.youtube.com/shorts/skV0hDd-chM"}))
        self.assertFalse(is_youtube_short({"source": "hackernews", "url": "https://www.youtube.com/watch?v=skV0hDd-chM"}))


if __name__ == "__main__":
    unittest.main()

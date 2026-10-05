import unittest
from unittest.mock import patch

from src.signals.content_briefing import content_headline, select_evidence
from src.signals.korean_briefing import build_korean_briefing
from src.signals.provenance import source_metadata
from src.sources.article_content import parse_article, article_context, validate_public_url, fetch_article


class ContentBriefingTest(unittest.TestCase):
    def test_parser_reads_main_content_and_publisher_not_navigation(self):
        html = '''<html><head><title>Shared title</title><meta property="og:site_name" content="Atlas">
        <meta name="description" content="Every app on Atlas now comes with monitoring built in."></head>
        <body><nav><p>Subscribe to our wonderful newsletter and sign up today.</p></nav>
        <main><h1>App monitoring without installation</h1><p>Every app on Atlas now comes with <b>monitoring</b> built in.</p>
        <script>Secret tracking code should not appear in the article.</script>
        <p>A person approves every change before it leaves the company.</p></main>
        <footer><p>Bring two workflows to a call and subscribe to our newsletter.</p></footer></body></html>'''
        context = parse_article(html, "https://atlas.test/post")
        self.assertEqual(context["site_name"], "Atlas")
        self.assertNotIn("Subscribe", context["text"])
        self.assertNotIn("tracking code", context["text"])
        self.assertIn("monitoring built in", context["text"])
        source = source_metadata({"source": "hackernews", "url": "https://atlas.test/post", "raw_json": {"article_context": context}})
        self.assertEqual(source["source_display"], "Atlas")
        self.assertEqual(source["collected_via"], "Hacker News")

    def test_parser_rejects_author_h1_and_selects_content_title(self):
        html = '''<html><head><title>Jane Doe | Atlas</title><meta property="og:site_name" content="Atlas">
        <meta property="og:title" content="How product teams evaluate AI agents"><meta name="author" content="Jane Doe">
        <meta name="description" content="A practical guide to evaluating AI agents in product teams."></head>
        <body><main><h1>Jane Doe</h1><p>Product teams evaluate AI agents with task success, safety checks, and human review.</p>
        <p>The guide compares evaluation methods for production workflows.</p></main></body></html>'''
        context = parse_article(html, "https://atlas.test/ai-agents")
        self.assertEqual(context["title"], "How product teams evaluate AI agents")
        self.assertEqual(context["title_basis"], "og_title")

    def test_parser_prefers_relevant_collector_title_over_unrelated_publication_h1(self):
        html = '''<html><head><title>twenty-first-century blues</title><meta name="description" content="How a book marketing scam works."></head>
        <body><main><h1>twenty-first-century blues</h1><p>I set a trap for a book-marketing scammer and documented the messages.</p>
        <p>The marketing pitch asked for payment before any promotion began.</p></main></body></html>'''
        context = parse_article(html, "https://example.test/post", fallback_title="I set a trap for a book-marketing scammer (2025)")
        self.assertEqual(context["title"], "I set a trap for a book-marketing scammer (2025)")
        self.assertEqual(context["title_basis"], "source_title")

    def test_content_drives_headline_instead_of_emotional_submitted_title(self):
        context = {"status": "available", "basis": "public_page", "site_name": "Atlas",
                   "title": "Monitoring without installation", "text": "Every app on Atlas now comes with monitoring built in. Response times and error logs are available to the assistant."}
        with patch("src.signals.korean_briefing.translate_to_korean", side_effect=lambda text: {"monitoring": "모니터링"}.get(text)):
            result = build_korean_briefing("Show HN: This changes everything", "", content_context=context)
        self.assertEqual(result["display_title_ko"], "Atlas, 모든 앱에 모니터링 기본 제공")
        self.assertNotIn("changes everything", result["display_title_ko"])
        self.assertEqual(result["original_title"], "Show HN: This changes everything")
        self.assertIn("Every app on Atlas", result["headline_evidence"])
        self.assertTrue(result["summary_evidence"])

    def test_company_operations_headline_and_human_approval_are_grounded(self):
        text = "An AI agent does the routine work of running our company. It sorts email and drafts invoices for our team. A person approves anything that leaves the company."
        title, evidence = content_headline("An inside look", "", text, "Northwind", lambda s: s)
        self.assertEqual(title, "Northwind, AI 에이전트로 회사의 반복 업무 처리")
        self.assertIn(evidence, text)
        selected = select_evidence("How we run our operations", "", text)
        self.assertIn("A person approves anything that leaves the company.", selected)

    def test_discussion_uses_described_feature_without_inventing_a_release(self):
        text = "I am worried about this. He's working on a feature that does automated reporting using Atlas, so fewer manual steps. He intends to test it next year."
        title, evidence = content_headline("Ask HN: I need a shower", "", text, "", lambda _: "Atlas를 활용한 자동 보고")
        self.assertEqual(title, "Atlas를 활용한 자동 보고 기능 개발에 대한 고민")
        self.assertNotIn("출시", title)
        self.assertIn(evidence, text)

    def test_missing_content_does_not_invent_details(self):
        with patch("src.signals.korean_briefing.translate_to_korean", return_value=None):
            result = build_korean_briefing("Ask HN: Any advice?", "", content_context={"status": "unavailable"})
        self.assertIn("제목만 확보", result["detail_limitation_ko"])
        self.assertEqual(result["summary_evidence"], [])

    def test_saved_hn_post_is_used_without_fetch_and_mock_never_fetches(self):
        with patch("src.sources.article_content.fetch_article") as fetch:
            context = article_context({"source": "hackernews", "url": "https://news.ycombinator.com/item?id=1",
                                       "raw_json": {"search_text": "A complete community post about a new automation workflow."}})
            self.assertEqual(context["basis"], "post_text")
            article_context({"source": "hackernews", "url": "https://example.com/sample", "raw_json": {"mock": True}})
            fetch.assert_not_called()

    def test_private_urls_and_redirect_destinations_are_rejected(self):
        for url in ["file:///C:/secret", "http://user:pass@example.org", "https://example.org:8000"]:
            with self.assertRaises(ValueError):
                validate_public_url(url)
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 80))]):
            with self.assertRaises(ValueError):
                validate_public_url("http://localhost/")
            result = fetch_article("http://localhost/")
            self.assertEqual(result["status"], "unavailable")

    def test_evidence_omits_ads_preambles_and_unfinished_headings(self):
        text = "Just to preface, this is not a typical coding story. Every app now includes monitoring: Subscribe to our newsletter today. A person approves changes before deployment."
        selected = select_evidence("Monitoring", "", text)
        self.assertFalse(any(s.startswith("Just to preface") for s in selected))
        self.assertFalse(any(s.endswith(":") for s in selected))


if __name__ == "__main__":
    unittest.main()

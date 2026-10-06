import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_store
from src.api.signals import router
from src.api.feedback import router as feedback_router
from src.signals.generator import SignalGenerator
from src.signals.korean_briefing import build_korean_briefing
from src.signals.provenance import source_metadata
from src.signals.identity import article_key
from src.signals.pipeline import SignalPipeline
from src.sources.collectors.base import CollectedItem, CollectorResult
from src.sources.collectors.hackernews import HackerNewsCollector
from src.sources.collectors.rss import RSSCollector
from src.sources.collectors.base import SourceQuery
from src.storage.sqlite_store import SQLiteStore


class TodaySignalsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "test.db")
        translation_patch = patch("src.signals.korean_briefing.translate_to_korean", return_value=None)
        self.translation = translation_patch.start()
        self.addCleanup(translation_patch.stop)
        article_patch = patch("src.sources.article_content.fetch_article", return_value={"status": "unavailable"})
        article_patch.start()
        self.addCleanup(article_patch.stop)
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.include_router(feedback_router, prefix="/api/v1")
        app.dependency_overrides[get_store] = lambda: self.store
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def generate(self, count=8, replace=True):
        run_id = self.store.create_pipeline_run("signal_generation")
        rows = [{"id": index, "title": f"마케팅 연구 {index}", "summary": f"실험 {index}에 대한 설명",
                 "source": "rss", "url": f"https://publisher.test/{index}", "score": 1 - index / 100,
                 "matched_keywords_json": ["마케팅"], "raw_json": {"data_kind": "live", "generation_mode": "hybrid"}}
                for index in range(count)]
        signals = SignalGenerator(self.store).generate_from_candidates(rows, replace_today=replace, pipeline_run_id=run_id)
        return run_id, signals

    def more(self, run_id):
        return self.client.post("/api/v1/signals/more", json={"pipeline_run_id": run_id})

    def test_ranked_pages_persist_feedback_and_keep_base_count(self):
        run_id, signals = self.generate()
        self.assertEqual(len(signals), 3)
        first = self.more(run_id).json()
        self.assertEqual([s["title"] for s in first["signals"]], [f"마케팅 연구 {i}" for i in range(6)])
        self.assertEqual([s["rank"] for s in first["signals"]], list(range(1, 7)))
        self.assertTrue(first["has_more"])
        extra_id = first["signals"][-1]["id"]
        feedback = self.client.post(f"/api/v1/signals/{extra_id}/feedback", json={"event_type": "saved", "payload": {}})
        self.assertEqual(feedback.status_code, 200)
        second = self.more(run_id).json()
        self.assertEqual(len(second["signals"]), 8)
        self.assertFalse(second["has_more"])
        self.assertEqual(len(self.more(run_id).json()["signals"]), 8)
        reopened = SQLiteStore(self.store.db_path)
        self.assertEqual(len(reopened.get_today_active_signals()), 8)
        self.assertEqual(reopened.get_signal(extra_id)["status"], "saved")
        self.assertEqual(reopened.get_settings()["signal_count"], 3)
        self.assertEqual(reopened.get_signal(extra_id)["source_url"], "https://publisher.test/5")

    def test_today_endpoint_keeps_feedback_cards_after_reopening(self):
        _, signals = self.generate(3)
        feedback_types = ("saved", "ignored", "tracked")
        for signal, event_type in zip(signals, feedback_types):
            response = self.client.post(
                f"/api/v1/signals/{signal['id']}/feedback",
                json={"event_type": event_type, "payload": {}},
            )
            self.assertEqual(response.status_code, 200)

        # The endpoint is used whenever the user returns to the Today tab.
        # Feedback changes future recommendations, not this day's snapshot.
        reopened_signals = self.client.get("/api/v1/signals/today").json()["signals"]
        self.assertEqual(
            {signal["id"] for signal in reopened_signals},
            {signal["id"] for signal in signals},
        )

    def test_short_empty_and_stale_runs(self):
        self.assertFalse(self.client.get("/api/v1/signals/today").json()["has_more"])
        run_id, signals = self.generate(2)
        self.assertEqual(len(signals), 2)
        self.assertFalse(self.more(run_id).json()["has_more"])
        new_run, _ = self.generate(5)
        self.assertEqual(self.more(run_id).status_code, 409)
        self.assertEqual(len(self.more(new_run).json()["signals"]), 5)
        self.generate(0)
        self.assertEqual(self.more(new_run).status_code, 409)
        self.assertEqual(self.store.get_today_active_signals(), [])

    def test_reserve_snapshot_and_duplicate_reveal_are_atomic(self):
        run_id, _ = self.generate()
        generator = SignalGenerator(self.store)
        prepared = [(rank, generator._build_signal(candidate, {}, [], rank))
                    for rank, candidate in self.store.get_signal_reserves(run_id)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.store.reveal_signals, run_id, prepared) for _ in range(2)]
            for future in futures:
                future.result()
        self.assertEqual(len(self.store.get_today_active_signals()), 6)
        self.assertEqual(len({s["source_url"] for s in self.store.get_today_active_signals()}), 6)
        self.assertEqual(len(SQLiteStore(self.store.db_path).get_signal_reserves(run_id)), 2)

    def test_duplicates_do_not_reappear_in_reserves(self):
        rows = [{"title": "마케팅", "source": "rss", "url": url, "score": .5}
                for url in ["https://a.test/1", "http://www.a.test/1?utm_source=hn", "https://a.test/2",
                            "https://a.test/3", "https://a.test/4", "https://a.test/4#fragment"]]
        run_id = self.store.create_pipeline_run("signal_generation")
        SignalGenerator(self.store).generate_from_candidates(rows, pipeline_run_id=run_id)
        result = self.more(run_id).json()
        self.assertEqual(len(result["signals"]), 4)
        self.assertFalse(result["has_more"])

    def test_youtube_link_variants_share_identity(self):
        links = ["https://youtu.be/abc123?si=share", "https://www.youtube.com/watch?v=abc123&t=20",
                 "https://m.youtube.com/shorts/abc123", "https://youtube.com/embed/abc123"]
        self.assertEqual(len({article_key({"url": url}) for url in links}), 1)
        self.assertNotEqual(article_key({"url": links[0]}), article_key({"url": "https://youtube.com/watch?v=other"}))

    def test_hybrid_collection_preserves_item_kind_in_basic_and_extra_cards(self):
        result = CollectorResult(source="hackernews", items=[
            CollectedItem(source="hackernews", source_item_id="real", url="https://youtu.be/abc", title="마케팅 영상"),
            CollectedItem(source="hackernews", source_item_id="sample", url="https://example.com/sample", title="마케팅 예시", raw_json={"mock": True}),
        ])
        run_id = self.store.create_pipeline_run("signal_generation")
        with patch("src.signals.pipeline.CollectorRegistry.collect", return_value=result):
            collection = SignalPipeline(self.store).collect_source_items(
                [{"source": "hackernews", "queries": [{"query": "마케팅"}]}], pipeline_run_id=run_id, mode="hybrid")
        self.store.update_settings({"signal_count": 1})
        signals = SignalGenerator(self.store).generate_from_candidates(collection["source_items"], pipeline_run_id=run_id)
        self.assertEqual(signals[0]["source_display"], "YouTube")
        self.assertEqual(signals[0]["data_kind"], "live")
        self.assertEqual(signals[0]["generation_mode"], "hybrid")
        extra = self.more(run_id).json()["signals"][1]
        self.assertEqual(extra["source_display"], "샘플 데이터")
        self.assertEqual(extra["data_kind"], "mock")
        self.assertEqual(extra["generation_mode"], "hybrid")
        self.assertEqual(self.store.get_settings()["signal_count"], 1)

    def test_prepared_page_cannot_restore_replaced_briefing(self):
        run_id, _ = self.generate()
        prepared = [(rank, SignalGenerator(self.store)._build_signal(candidate, {}, [], rank))
                    for rank, candidate in self.store.get_signal_reserves(run_id)]
        self.generate(1)
        with self.assertRaises(ValueError):
            self.store.reveal_signals(run_id, prepared)
        self.assertEqual(len(self.store.get_today_active_signals()), 1)

    def test_source_uses_original_host_and_feed_metadata_not_headline(self):
        collector = HackerNewsCollector()
        item = collector._normalize_story({"id": 1, "title": "Video", "url": "https://www.youtube.com/watch?v=abc"}, None).to_dict()
        metadata = source_metadata(item)
        self.assertEqual(metadata["source_display"], "YouTube")
        self.assertEqual(metadata["collected_via"], "Hacker News")
        self.assertEqual(source_metadata({"source": "rss", "url": "https://youtu.be/abc"})["source_display"], "YouTube")
        self.assertNotEqual(source_metadata({"source": "hackernews", "title": "YouTube", "url": "https://youtube.com.evil.test/a"})["source_display"], "YouTube")
        xml = '<rss><channel><title>연구소 소식</title><item><title>새 연구</title><link>https://lab.test/research</link><description>연구 설명</description></item></channel></rss>'
        item = RSSCollector(fetch_text=lambda *_: xml).collect([SourceQuery("rss", "", {"feed_url": "https://lab.test/rss"})], 3).item_dicts()[0]
        self.assertEqual(source_metadata(item)["source_display"], "연구소 소식")
        item["raw_json"]["mock"] = True
        self.assertEqual(source_metadata(item)["source_display"], "샘플 데이터")

    def test_grounded_korean_explanation_and_post_format(self):
        mapping = {"How do you evaluate AI agents?": "당신은 AI 에이전트를 어떻게 평가합니까?",
                   "We compared two tools.": "두 도구를 비교했습니다."}
        self.translation.side_effect = lambda text: mapping.get(text)
        result = build_korean_briefing("Ask HN: How do you evaluate AI agents?", "<p>We compared two tools.</p>")
        self.assertEqual(result["display_title_ko"], "AI 에이전트를 어떻게 평가하나요?")
        self.assertNotIn("Ask HN", result["display_title_ko"])
        self.assertIn("두 도구를 비교했습니다.", result["detail_summary_ko"])
        self.assertNotIn("성능 향상", result["detail_summary_ko"])
        self.assertIn("원문 전체나 영상", result["detail_limitation_ko"])
        self.assertEqual(result["original_title"], "Ask HN: How do you evaluate AI agents?")
        self.assertNotIn("Ask HN", self.translation.call_args_list[0].args[0])

    def test_missing_description_and_failed_translation_are_honest(self):
        result = build_korean_briefing("Show HN: An open source tool", "")
        self.assertEqual(result["display_title_ko"], "An open source tool")
        self.assertIn("제목만 확보", result["detail_limitation_ko"])
        self.assertNotIn("제공된 설명:", result["detail_summary_ko"])
        self.assertIn("번역을 확보하지 못한", result["detail_limitation_ko"])

    def test_existing_rows_upgrade_without_changing_links_or_feedback(self):
        signal_id = self.store.create_signal({"title": "Ask HN: 한국어 질문", "summary": "설명", "why_it_matters": "",
                                             "source_url": "https://youtu.be/abc", "source_name": "hackernews", "status": "saved",
                                             "metadata_json": {"briefing_version": 4}})
        signal = self.store.get_signal(signal_id)
        self.assertEqual(signal["display_title_ko"], "한국어 질문")
        self.assertEqual(signal["source_display"], "YouTube")
        self.assertEqual(signal["status"], "saved")
        self.assertEqual(signal["source_url"], "https://youtu.be/abc")
        self.assertFalse(self.store.signal_expansion_status()["has_more"])

    def test_legacy_mock_endpoint_labels_samples(self):
        result = self.client.post("/api/v1/signals/generate-mock").json()
        self.assertEqual(result["count"], 3)
        for signal in result["signals"]:
            self.assertEqual(signal["source_display"], "샘플 데이터")
            self.assertEqual(signal["data_kind"], "mock")
            self.assertEqual(signal["generation_mode"], "mock")

    def test_period_briefings_prefer_published_time_fallback_and_dedupe(self):
        def add(title, url, confidence, published_at=None):
            signal_id = self.store.create_signal({
                "title": title, "summary": "summary", "why_it_matters": "why",
                "source_name": "rss", "source_url": url, "confidence": confidence,
                "status": "active", "source_items_json": [{"url": url, "published_at": published_at}],
                "metadata_json": {"briefing_version": 9, "published_at": published_at},
            })
            return signal_id

        recent_id = add("today", "https://period.test/today", .4, "2026-10-06T01:00:00Z")
        week_id = add("week", "https://period.test/week", .9, "2026-10-02T10:00:00Z")
        month_id = add("month", "https://period.test/month", .7, "2026-09-15T10:00:00Z")
        old_id = add("old", "https://period.test/old", .99, "2026-08-01T10:00:00Z")
        fallback_id = add("fallback", "https://period.test/fallback", .8)
        duplicate_id = add("duplicate", "https://period.test/week", .95, "2026-10-02T10:00:00Z")
        with self.store.connect() as conn:
            conn.execute("UPDATE signals SET created_at = ? WHERE id = ?", ("2026-10-05 12:00:00", fallback_id))
            conn.commit()

        reference = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
        today = self.store.get_signals_for_period("today", now=reference)
        week = self.store.get_signals_for_period("week", now=reference)
        month = self.store.get_signals_for_period("month", now=reference)

        self.assertEqual({item["id"] for item in today}, {recent_id, fallback_id})
        self.assertEqual({item["id"] for item in week}, {recent_id, fallback_id, duplicate_id})
        self.assertEqual({item["id"] for item in month}, {recent_id, month_id, fallback_id, duplicate_id})
        self.assertNotIn(old_id, {item["id"] for item in month})
        self.assertEqual(len([item for item in week if item["source_url"] == "https://period.test/week"]), 1)
        self.assertEqual(week[0]["id"], duplicate_id)

    def test_period_endpoint_and_validation(self):
        self.store.create_signal({"title": "period", "summary": "summary", "why_it_matters": "why",
                                  "source_url": "https://period.test/api", "status": "active",
                                  "metadata_json": {"briefing_version": 9, "published_at": "2026-10-06T10:00:00Z"}})
        response = self.client.get("/api/v1/signals?period=week")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["period"], "week")
        self.assertFalse(response.json()["has_more"])
        self.assertEqual(self.client.get("/api/v1/signals?period=year").status_code, 422)


if __name__ == "__main__":
    unittest.main()

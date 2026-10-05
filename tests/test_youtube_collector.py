import unittest

from src.sources.collectors.base import SourceQuery
from src.sources.collectors.youtube import YouTubeCollector


class YouTubeCollectorTests(unittest.TestCase):
    def test_requires_api_key(self):
        result = YouTubeCollector(api_key="").collect([SourceQuery(source="youtube", query="AI")], limit=2)
        self.assertEqual(result.items, [])
        self.assertTrue(result.errors)

    def test_collects_verified_video_and_channel_metadata_in_three_batched_calls(self):
        calls = []

        def fetch(url, _timeout):
            calls.append(url)
            if "/search?" in url:
                return {"items": [{"id": {"videoId": "video-123"}}]}
            if "/videos?" in url:
                return {"items": [{
                    "id": "video-123",
                    "snippet": {"title": "AI &amp; product update", "description": "AI product workflow overview",
                                "channelTitle": "LUMOS Research", "channelId": "channel-123",
                                "publishedAt": "2026-10-01T02:00:00Z", "tags": ["AI", "product"],
                                "thumbnails": {"high": {"url": "https://img.example/video.jpg"}}},
                    "statistics": {"viewCount": "9000", "likeCount": "450", "commentCount": "90"},
                    "contentDetails": {"duration": "PT12M"},
                }]}
            return {"items": [{
                "id": "channel-123",
                "snippet": {"title": "LUMOS Research", "description": "Independent AI research and analysis.",
                            "publishedAt": "2020-01-01T00:00:00Z"},
                "statistics": {"subscriberCount": "25000", "videoCount": "80", "viewCount": "2000000"},
            }]}

        collector = YouTubeCollector(fetch_json=fetch, api_key="test-key")
        result = collector.collect([SourceQuery(source="youtube", query="AI product", route_id=7, category="AI_LLM_AGENT")], limit=2)

        self.assertEqual(len(result.items), 1)
        self.assertEqual(len(calls), 3)
        item = result.items[0]
        self.assertEqual(item.source_item_id, "video-123")
        self.assertEqual(item.title, "AI & product update")
        self.assertEqual(item.url, "https://www.youtube.com/watch?v=video-123")
        self.assertEqual(item.metrics_json["views"], 9000)
        self.assertEqual(item.raw_json["channel_metadata"]["subscriberCount"], 25000)
        self.assertEqual(item.raw_json["content_language"], "en")
        scoring = item.raw_json["youtube_scoring"]
        self.assertIn(scoring["sourceType"], {"ACADEMIC", "EXPERT", "CREATOR", "UNKNOWN"})
        self.assertGreater(scoring["relevanceScore"], 20)
        self.assertGreaterEqual(scoring["finalScore"], 0)
        self.assertLessEqual(scoring["finalScore"], 100)

    def test_trusted_academic_channel_bypasses_popularity_filter(self):
        collector = YouTubeCollector(api_key="test-key")
        scoring = collector._score(
            {"snippet": {"title": "Research update", "channelTitle": "POSTECH University",
                         "description": "", "publishedAt": "2026-01-01T00:00:00Z"},
             "statistics": {"viewCount": "1000"}, "contentDetails": {"duration": "PT4M"}},
            {"snippet": {"title": "POSTECH University", "description": "University research institute",
                         "publishedAt": "2020-01-01T00:00:00Z"},
             "statistics": {"subscriberCount": "100", "videoCount": "2", "viewCount": "1000"}},
            SourceQuery(source="youtube", query="research", category="RESEARCH"),
        )
        self.assertEqual(scoring["sourceType"], "ACADEMIC")
        self.assertTrue(scoring["eligible"])

    def test_video_below_absolute_view_floor_is_not_eligible_even_when_trusted(self):
        collector = YouTubeCollector(api_key="test-key")
        scoring = collector._score(
            {"snippet": {"title": "Research update", "channelTitle": "POSTECH University",
                         "publishedAt": "2026-01-01T00:00:00Z"},
             "statistics": {"viewCount": "999"}, "contentDetails": {"duration": "PT4M"}},
            {"snippet": {"title": "POSTECH University", "description": "University research institute",
                         "publishedAt": "2020-01-01T00:00:00Z"},
             "statistics": {"subscriberCount": "100", "videoCount": "2", "viewCount": "1000"}},
            SourceQuery(source="youtube", query="research", category="RESEARCH"),
        )
        self.assertFalse(scoring["eligible"])

    def test_short_video_is_not_eligible_for_general_recommendations(self):
        collector = YouTubeCollector(api_key="test-key")
        scoring = collector._score(
            {"snippet": {"title": "AI #shorts", "channelTitle": "Popular Creator", "publishedAt": "2026-01-01T00:00:00Z"},
             "statistics": {"viewCount": "1000000"}, "contentDetails": {"duration": "PT45S"}},
            {"snippet": {"title": "Popular Creator", "publishedAt": "2020-01-01T00:00:00Z"},
             "statistics": {"subscriberCount": "100000", "videoCount": "200", "viewCount": "10000000"}},
            SourceQuery(source="youtube", query="AI", category="AI_LLM_AGENT"),
        )
        self.assertTrue(scoring["isShort"])
        self.assertFalse(scoring["eligible"])


if __name__ == "__main__":
    unittest.main()

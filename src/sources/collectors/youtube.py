import json
import math
import os
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery
from src.sources.youtube_config import (
    AUTHORITY_WEIGHT, CANDIDATE_POOL_SIZE, CHANNEL_WEIGHT, FRESHNESS_HALF_LIFE_DAYS,
    FRESHNESS_WEIGHT, MIN_CHANNEL_VIDEOS, MIN_DURATION_SECONDS, MIN_SUBSCRIBERS,
    MIN_VIDEO_VIEWS, MIN_VIDEO_VIEWS_FLOOR, PERFORMANCE_WEIGHT, RELEVANCE_WEIGHT, SOURCE_TYPE_SCORES,
    TRUSTED_SOURCE_TYPES, YOUTUBE_BATCH_SIZE,
)


class YouTubeCollector(BaseCollector):
    """Find a bounded pool, then rank verified video/channel metadata in batches."""

    source_id = "youtube"
    SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
    VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
    CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
    TYPE_TERMS = {
        "OFFICIAL": ("official", "government", "ministry", "department", "정부", "공식", "inc.", "ltd", "corp"),
        "ACADEMIC": ("university", "college", "institute", "research", "laboratory", "lab", "대학교", "대학", "연구원", "학회"),
        "MEDIA": ("news", "media", "broadcast", "times", "journal", "일보", "뉴스", "방송"),
        "EXPERT": ("professor", "prof.", "phd", "doctor", "dr.", "analyst", "researcher", "교수", "박사", "연구자"),
        "CREATOR": ("creator", "studio", "tv", "channel", "튜브", "크리에이터"),
    }

    def __init__(self, fetch_json: Optional[Callable[[str, float], Any]] = None,
                 api_key: Optional[str] = None, timeout: float = 7.0):
        self.fetch_json = fetch_json or self._fetch_json
        self.api_key = (api_key if api_key is not None else os.environ.get("YOUTUBE_API_KEY", "")).strip()
        self.timeout = timeout

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        if not self.api_key:
            return CollectorResult(source=self.source_id, errors=["YouTube API 키가 필요해요. YOUTUBE_API_KEY 환경변수를 설정해주세요."])
        queries = [query for query in queries if query.query.strip()]
        if not queries:
            return CollectorResult(source=self.source_id)
        errors: List[str] = []
        candidates = self._search(queries, errors)
        if not candidates:
            return CollectorResult(source=self.source_id, errors=errors)
        videos = self._batch(self.VIDEOS_URL, candidates, "snippet,statistics,contentDetails", "videos", errors)
        if not videos:
            return CollectorResult(source=self.source_id, errors=errors, warnings=["Video details unavailable; search snippets were not recommended."])
        channels = self._batch(self.CHANNELS_URL, [str((v.get("snippet") or {}).get("channelId") or "") for v in videos.values()],
                               "snippet,statistics", "channels", errors)
        ranked: List[Tuple[float, CollectedItem]] = []
        for video_id, query in candidates.items():
            video = videos.get(video_id)
            if not video:
                continue
            channel = channels.get(str((video.get("snippet") or {}).get("channelId") or ""), {})
            scoring = self._score(video, channel, query)
            if not scoring["eligible"]:
                continue
            item = self._normalize_video(video, channel, query, scoring)
            if item:
                ranked.append((scoring["finalScore"], item))
        ranked.sort(key=lambda entry: (-entry[0], entry[1].source_item_id))
        warnings = [] if channels else ["Channel details unavailable; only trusted/verified metadata was evaluated."]
        return CollectorResult(source=self.source_id, items=[item for _, item in ranked[:max(1, limit)]], errors=errors, warnings=warnings)

    def _search(self, queries: List[SourceQuery], errors: List[str]) -> Dict[str, SourceQuery]:
        per_query = max(1, min(50, math.ceil(CANDIDATE_POOL_SIZE / len(queries))))
        candidates: Dict[str, SourceQuery] = {}
        for query in queries:
            params: Dict[str, Any] = {"part": "snippet", "type": "video", "order": "date", "q": query.query,
                                      "maxResults": per_query, "key": self.api_key}
            if (query.params or {}).get("language"):
                params["relevanceLanguage"] = str(query.params["language"])[:2]
            if (query.params or {}).get("region"):
                params["regionCode"] = str(query.params["region"]).upper()[:2]
            try:
                payload = self.fetch_json(f"{self.SEARCH_URL}?{urlencode(params)}", self.timeout) or {}
                for entry in payload.get("items", []):
                    video_id = str((entry.get("id") or {}).get("videoId") or "").strip()
                    if video_id:
                        candidates.setdefault(video_id, query)
                    if len(candidates) >= CANDIDATE_POOL_SIZE:
                        return candidates
            except Exception as exc:
                errors.append(f"search {query.query}: {exc}")
        return candidates

    def _batch(self, endpoint: str, ids: Iterable[str], part: str, label: str, errors: List[str]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        unique = list(dict.fromkeys(value for value in ids if value))
        for offset in range(0, len(unique), YOUTUBE_BATCH_SIZE):
            batch = unique[offset:offset + YOUTUBE_BATCH_SIZE]
            try:
                payload = self.fetch_json(f"{endpoint}?{urlencode({'part': part, 'id': ','.join(batch), 'key': self.api_key})}", self.timeout) or {}
                result.update({str(item.get("id")): item for item in payload.get("items", []) if item.get("id")})
            except Exception as exc:
                errors.append(f"{label} details: {exc}")
        return result

    def _score(self, video: Dict[str, Any], channel: Dict[str, Any], query: SourceQuery) -> Dict[str, Any]:
        snippet, stats = video.get("snippet") or {}, video.get("statistics") or {}
        channel_snippet, channel_stats = channel.get("snippet") or {}, channel.get("statistics") or {}
        duration = self._duration((video.get("contentDetails") or {}).get("duration"))
        source_type = self._source_type(snippet, channel_snippet)
        # Authority exemptions require a returned channel record; a video title
        # alone must not be able to impersonate an official source.
        trusted = bool(channel) and source_type in TRUSTED_SOURCE_TYPES
        subscribers, channel_videos, views = (self._number(channel_stats.get("subscriberCount")),
                                               self._number(channel_stats.get("videoCount")), self._number(stats.get("viewCount")))
        is_short = duration < MIN_DURATION_SECONDS or self._is_short(snippet, duration)
        searchable_text = " ".join(str(value or "") for value in (snippet.get("title"), snippet.get("description"),
                                                                      " ".join(snippet.get("tags") or []))).casefold()
        semantic_excludes = [str(term).casefold() for term in (query.params or {}).get("semantic_excludes", [])]
        semantic_excluded = any(term and term in searchable_text for term in semantic_excludes)
        eligible = not semantic_excluded and not is_short and views >= MIN_VIDEO_VIEWS_FLOOR and (
            trusted or (subscribers >= MIN_SUBSCRIBERS and channel_videos >= MIN_CHANNEL_VIDEOS and views >= MIN_VIDEO_VIEWS)
        )
        authority = min(100.0, SOURCE_TYPE_SCORES[source_type] + (4 if len(str(channel_snippet.get("description") or "")) >= 80 else 0))
        relevance = self._relevance(snippet, query.query)
        channel_score = self._channel_score(channel_stats, channel_snippet.get("publishedAt"))
        performance = self._performance(stats, subscribers)
        freshness = self._freshness(snippet.get("publishedAt"), query)
        final = authority * AUTHORITY_WEIGHT + relevance * RELEVANCE_WEIGHT + channel_score * CHANNEL_WEIGHT + performance * PERFORMANCE_WEIGHT + freshness * FRESHNESS_WEIGHT
        if is_short:
            final *= 0.65
        return {"eligible": eligible, "sourceType": source_type, "authorityScore": round(authority, 2),
                "relevanceScore": round(relevance, 2), "channelScore": round(channel_score, 2),
                "performanceScore": round(performance, 2), "freshnessScore": round(freshness, 2),
                "finalScore": round(max(0.0, min(100.0, final)), 2), "trustedSource": trusted,
                "isShort": is_short, "semanticExcluded": semantic_excluded, "durationSeconds": duration,
                "filter": {"subscribers": subscribers, "channelVideos": channel_videos, "videoViews": views,
                           "minimumVideoViews": MIN_VIDEO_VIEWS_FLOOR, "minimumDurationSeconds": MIN_DURATION_SECONDS}}

    def _normalize_video(self, entry: Dict[str, Any], channel: Dict[str, Any], query: SourceQuery,
                         scoring: Dict[str, Any]) -> Optional[CollectedItem]:
        video_id, snippet = str(entry.get("id") or "").strip(), entry.get("snippet") or {}
        title = unescape(str(snippet.get("title") or "").strip())
        if not video_id or not title:
            return None
        thumbnails = snippet.get("thumbnails") or {}
        thumbnail = thumbnails.get("high") or thumbnails.get("medium") or thumbnails.get("default") or {}
        stats = entry.get("statistics") or {}
        return CollectedItem(source=self.source_id, source_item_id=video_id, url=f"https://www.youtube.com/watch?v={video_id}",
            title=title[:300], summary=unescape(str(snippet.get("description") or "").strip())[:500],
            author=str(snippet.get("channelTitle") or "").strip(), published_at=snippet.get("publishedAt"),
            metrics_json={"views": self._number(stats.get("viewCount")), "likes": self._number(stats.get("likeCount")),
                          "comments": self._number(stats.get("commentCount")), "duration_seconds": scoring["durationSeconds"]},
            raw_json={"youtube_video_id": video_id, "channel_id": snippet.get("channelId"), "thumbnail_url": thumbnail.get("url"),
                      "tags": list(snippet.get("tags") or [])[:25], "youtube_query": query.query,
                      "content_language": self._content_language(f"{title} {snippet.get('description') or ''}"),
                      "channel_metadata": {"subscriberCount": self._number((channel.get("statistics") or {}).get("subscriberCount")),
                                           "videoCount": self._number((channel.get("statistics") or {}).get("videoCount")),
                                           "viewCount": self._number((channel.get("statistics") or {}).get("viewCount")),
                                           "publishedAt": (channel.get("snippet") or {}).get("publishedAt")},
                      "duration_seconds": scoring["durationSeconds"], "youtube_scoring": scoring}, route_id=query.route_id)

    def _source_type(self, video: Dict[str, Any], channel: Dict[str, Any]) -> str:
        text = " ".join(str(value or "") for value in (video.get("channelTitle"), channel.get("title"), channel.get("description"), video.get("title"))).casefold()
        for source_type in ("OFFICIAL", "ACADEMIC", "MEDIA", "EXPERT", "CREATOR"):
            if any(term.casefold() in text for term in self.TYPE_TERMS[source_type]):
                return source_type
        return "UNKNOWN"

    def _relevance(self, snippet: Dict[str, Any], query: str) -> float:
        title, description = str(snippet.get("title") or "").casefold(), str(snippet.get("description") or "").casefold()
        tags = " ".join(str(tag) for tag in snippet.get("tags") or []).casefold()
        terms = [term for term in re.findall(r"[\w가-힣+#.]{2,}", query.casefold()) if term not in {"trend", "video"}]
        if not terms:
            return 50.0
        matches = sum((3 if term in title else 0) + (2 if term in tags else 0) + (1 if term in description else 0) for term in terms)
        return min(100.0, 20.0 + 80.0 * matches / (3 * len(terms)))

    def _channel_score(self, stats: Dict[str, Any], published_at: Any) -> float:
        subscribers, videos, views = self._number(stats.get("subscriberCount")), self._number(stats.get("videoCount")), self._number(stats.get("viewCount"))
        score = lambda value, cap: min(100.0, math.log10(value + 1) / cap * 100.0)
        return .40 * score(subscribers, 6) + .20 * score(videos, 3) + .25 * score(views, 8) + .15 * min(100.0, self._age_days(published_at) / 1825 * 100)

    def _performance(self, stats: Dict[str, Any], subscribers: int) -> float:
        views, likes, comments = self._number(stats.get("viewCount")), self._number(stats.get("likeCount")), self._number(stats.get("commentCount"))
        view_score = min(100.0, math.log10(views + 1) / 7 * 100)
        reach = min(100.0, min(3.0, views / max(1, subscribers)) / .5 * 100)
        likes_score = min(100.0, min(.20, likes / max(1, views)) / .05 * 100)
        comments_score = min(100.0, min(.05, comments / max(1, views)) / .01 * 100)
        return .35 * view_score + .30 * reach + .25 * likes_score + .10 * comments_score

    def _freshness(self, published_at: Any, query: SourceQuery) -> float:
        text = f"{query.category} {query.query}".casefold()
        if any(term in text for term in ("news", "뉴스", "breaking")): key = "news"
        elif any(term in text for term in ("finance", "financial", "stock", "경제", "금융")): key = "finance"
        elif any(term in text for term in ("science", "research", "paper", "과학", "연구")): key = "science"
        elif any(term in text for term in ("history", "philosophy", "역사", "철학")): key = "history_philosophy"
        elif any(term in text for term in ("career", "self", "productivity", "커리어", "자기계발")): key = "self_development"
        elif any(term in text for term in ("ai", "llm", "developer", "tech", "it", "개발", "인공지능")): key = "ai_it"
        else: key = "default"
        return 100.0 * math.exp(-math.log(2) * self._age_days(published_at) / FRESHNESS_HALF_LIFE_DAYS[key])

    @staticmethod
    def _duration(value: Any) -> int:
        match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", str(value or ""))
        if not match: return 0
        days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
        return days * 86400 + hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def _number(value: Any) -> int:
        try: return max(0, int(value or 0))
        except (TypeError, ValueError): return 0

    @staticmethod
    def _is_short(snippet: Dict[str, Any], duration: int) -> bool:
        return duration <= 60 or "#shorts" in f"{snippet.get('title', '')} {snippet.get('description', '')}".casefold()

    @staticmethod
    def _age_days(value: Any) -> float:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return max(0.0, (datetime.now(timezone.utc) - (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc))).total_seconds() / 86400)
        except (TypeError, ValueError): return 365.0

    @staticmethod
    def _content_language(text: str) -> str:
        korean = sum(1 for char in text if "가" <= char <= "힣")
        latin = sum(1 for char in text if char.isascii() and char.isalpha())
        if korean and korean >= latin * 0.15:
            return "ko"
        if latin:
            return "en"
        return "unknown"

    def _fetch_json(self, url: str, timeout: float):
        request = Request(url, headers={"User-Agent": "LUMOS/0.1"})
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))

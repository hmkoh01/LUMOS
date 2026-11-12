from typing import Dict, List, Optional

from src.sources.collectors.base import BaseCollector, CollectorResult, NoOpCollector, SourceQuery
from src.sources.collectors.github import GitHubCollector
from src.sources.collectors.hackernews import HackerNewsCollector
from src.sources.collectors.mock import MockCollector
from src.sources.collectors.rss import RSSCollector
from src.sources.collectors.youtube import YouTubeCollector
from src.sources.collectors.crossref import CrossrefCollector
from src.sources.collectors.mss_bizinfo import MSSBizInfoCollector
from src.sources.collectors.mss_support_program import MSSSupportProgramCollector
from src.sources.collectors.public_institution_jobs import PublicInstitutionJobsCollector
from src.sources.collectors.schema_pending import PublicServiceJobsCollector, SeoulCultureEventsCollector, YouthCenterPolicyCollector
from src.sources.collectors.work24 import Work24Collector
from src.sources.collectors.opendart import OpenDARTCollector
from src.sources.collectors.kopis import KOPISCollector
from src.sources.collectors.msit_announcements import MSITAnnouncementCollector
from src.sources.collectors.openalex import OpenAlexCollector
from src.sources.collectors.tourapi import TourAPIFestivalCollector


RSS_BACKED_SOURCES = {
    "rss", "official_ai_blogs", "company_newsroom", "geeknews", "kisa_press", "kisa_research",
    "msit_business_rss", "msit_recruitment_rss",
}
# This denotes a Collector implementation only; Source Registry permission and
# environment checks still decide whether a source can run in live collection.
IMPLEMENTED_SOURCES = {"mock", "hackernews", "github", "youtube", "crossref", "openalex", "mss_bizinfo", "mss_support_program", "msit_announcements", "tourapi", "public_institution_jobs", "public_service_jobs", "youthcenter_policy", "seoul_culture_events", "employment24", "opendart", "kopis", *RSS_BACKED_SOURCES}
PLACEHOLDER_SOURCES = {
    "producthunt",
    "reddit",
    "naver_news",
    "arxiv",
}

COLLECTOR_OVERRIDES: Dict[str, BaseCollector] = {}


class CollectorRegistry:
    def __init__(self, overrides: Optional[Dict[str, BaseCollector]] = None):
        self.overrides = overrides or COLLECTOR_OVERRIDES

    def get(self, source_id: str, mode: str = "mock") -> BaseCollector:
        mode = self.normalize_mode(mode)
        if source_id in self.overrides:
            return self.overrides[source_id]
        if mode == "mock":
            return MockCollector()
        if source_id in RSS_BACKED_SOURCES:
            return RSSCollector(source_id=source_id)
        if source_id == "hackernews":
            return HackerNewsCollector()
        if source_id == "github":
            return GitHubCollector()
        if source_id == "youtube":
            return YouTubeCollector()
        if source_id == "crossref":
            return CrossrefCollector()
        if source_id == "openalex":
            return OpenAlexCollector()
        if source_id == "mss_bizinfo":
            return MSSBizInfoCollector()
        if source_id == "mss_support_program":
            return MSSSupportProgramCollector()
        if source_id == "public_institution_jobs":
            return PublicInstitutionJobsCollector()
        if source_id == "public_service_jobs":
            return PublicServiceJobsCollector()
        if source_id == "youthcenter_policy":
            return YouthCenterPolicyCollector()
        if source_id == "seoul_culture_events":
            return SeoulCultureEventsCollector()
        if source_id == "employment24":
            return Work24Collector()
        if source_id == "opendart":
            return OpenDARTCollector()
        if source_id == "kopis":
            return KOPISCollector()
        if source_id == "msit_announcements":
            return MSITAnnouncementCollector()
        if source_id == "tourapi":
            return TourAPIFestivalCollector()
        if mode == "hybrid":
            return MockCollector()
        return NoOpCollector(source_id)

    def collect(self, source_id: str, queries: List[SourceQuery], limit: int, mode: str = "mock") -> CollectorResult:
        collector = self.get(source_id, mode=mode)
        if isinstance(collector, MockCollector):
            return collector.collect(queries, limit=limit)
        return collector.collect(queries, limit=limit)

    def support_status(self, source_id: str, mode: str = "mock") -> str:
        if source_id in self.overrides:
            return "implemented"
        if self.normalize_mode(mode) == "mock":
            return "mock"
        if source_id in IMPLEMENTED_SOURCES:
            return "implemented"
        if source_id in PLACEHOLDER_SOURCES:
            return "placeholder"
        return "unknown"

    def normalize_mode(self, mode: str) -> str:
        if mode not in {"mock", "hybrid", "live"}:
            return "mock"
        return mode

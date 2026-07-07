from dataclasses import dataclass
from dataclasses import asdict
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SourceMetadata:
    source_id: str
    display_name: str
    categories: List[str]
    default_limit: int
    trust_score: float
    freshness_weight: float
    community_weight: float
    enabled_by_default: bool
    description: str


SOURCE_REGISTRY: Dict[str, SourceMetadata] = {
    "official_ai_blogs": SourceMetadata(
        source_id="official_ai_blogs",
        display_name="Official AI Blogs",
        categories=["AI_LLM_AGENT", "RESEARCH"],
        default_limit=5,
        trust_score=0.95,
        freshness_weight=0.8,
        community_weight=0.2,
        enabled_by_default=True,
        description="High-trust official AI product and research updates.",
    ),
    "hackernews": SourceMetadata(
        source_id="hackernews",
        display_name="Hacker News",
        categories=["AI_LLM_AGENT", "STARTUP_PRODUCT", "DEVELOPER_TECH"],
        default_limit=8,
        trust_score=0.75,
        freshness_weight=0.75,
        community_weight=0.9,
        enabled_by_default=True,
        description="Developer and startup community reaction.",
    ),
    "github": SourceMetadata(
        source_id="github",
        display_name="GitHub",
        categories=["AI_LLM_AGENT", "DEVELOPER_TECH", "RESEARCH", "COMPANY_TRACKING"],
        default_limit=8,
        trust_score=0.8,
        freshness_weight=0.7,
        community_weight=0.75,
        enabled_by_default=True,
        description="Implementation movement across open source repositories.",
    ),
    "producthunt": SourceMetadata(
        source_id="producthunt",
        display_name="Product Hunt",
        categories=["STARTUP_PRODUCT"],
        default_limit=6,
        trust_score=0.65,
        freshness_weight=0.85,
        community_weight=0.8,
        enabled_by_default=False,
        description="New products, launches, and competitive discovery.",
    ),
    "reddit": SourceMetadata(
        source_id="reddit",
        display_name="Reddit",
        categories=["AI_LLM_AGENT", "STARTUP_PRODUCT", "DEVELOPER_TECH", "CONTENT_SNS", "CAREER"],
        default_limit=6,
        trust_score=0.45,
        freshness_weight=0.65,
        community_weight=0.85,
        enabled_by_default=False,
        description="Community reaction with higher noise.",
    ),
    "youtube": SourceMetadata(
        source_id="youtube",
        display_name="YouTube",
        categories=["CONTENT_SNS", "CAREER"],
        default_limit=5,
        trust_score=0.55,
        freshness_weight=0.6,
        community_weight=0.75,
        enabled_by_default=False,
        description="Creator and video trend signals.",
    ),
    "naver_news": SourceMetadata(
        source_id="naver_news",
        display_name="Naver News",
        categories=["DOMESTIC_INDUSTRY", "COMPANY_TRACKING", "CAREER"],
        default_limit=7,
        trust_score=0.7,
        freshness_weight=0.85,
        community_weight=0.35,
        enabled_by_default=False,
        description="Korean industry, company, and career news.",
    ),
    "rss": SourceMetadata(
        source_id="rss",
        display_name="RSS and Official Blogs",
        categories=["STARTUP_PRODUCT", "DEVELOPER_TECH", "CONTENT_SNS", "DOMESTIC_INDUSTRY", "COMPANY_TRACKING", "CAREER"],
        default_limit=8,
        trust_score=0.7,
        freshness_weight=0.75,
        community_weight=0.25,
        enabled_by_default=True,
        description="Configured feeds and official changelogs.",
    ),
    "arxiv": SourceMetadata(
        source_id="arxiv",
        display_name="arXiv",
        categories=["AI_LLM_AGENT", "RESEARCH"],
        default_limit=5,
        trust_score=0.85,
        freshness_weight=0.65,
        community_weight=0.25,
        enabled_by_default=False,
        description="Research and paper signals.",
    ),
    "company_newsroom": SourceMetadata(
        source_id="company_newsroom",
        display_name="Company Newsrooms",
        categories=["DOMESTIC_INDUSTRY", "COMPANY_TRACKING"],
        default_limit=5,
        trust_score=0.85,
        freshness_weight=0.8,
        community_weight=0.2,
        enabled_by_default=False,
        description="Company announcements and official updates.",
    ),
}


def get_source(source_id: str) -> SourceMetadata:
    return SOURCE_REGISTRY[source_id]


def list_sources() -> List[SourceMetadata]:
    return list(SOURCE_REGISTRY.values())


def get_source_catalog(configs: Optional[List[Dict[str, Any]]] = None, status_lookup=None) -> List[Dict[str, Any]]:
    config_map = {item["source_id"]: item for item in configs or []}
    catalog = []
    for source_id, metadata in SOURCE_REGISTRY.items():
        config = config_map.get(source_id, {})
        item = asdict(metadata)
        item["current_enabled"] = bool(config.get("enabled", metadata.enabled_by_default))
        item["priority"] = int(config.get("priority", 50))
        item["config_json"] = config.get("config_json", {})
        item["implemented_status"] = status_lookup(source_id) if status_lookup else "unknown"
        catalog.append(item)
    return sorted(catalog, key=lambda item: (not item["current_enabled"], -item["priority"], item["source_id"]))


def get_effective_source_config(source_id: str, configs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    metadata = SOURCE_REGISTRY[source_id]
    config_map = {item["source_id"]: item for item in configs or []}
    config = config_map.get(source_id, {})
    return {
        **asdict(metadata),
        "enabled": bool(config.get("enabled", metadata.enabled_by_default)),
        "priority": int(config.get("priority", 50)),
        "config_json": config.get("config_json", {}),
    }


def list_enabled_sources(configs: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    return [
        item["source_id"]
        for item in get_source_catalog(configs)
        if item["current_enabled"]
    ]

import os
from dataclasses import asdict, dataclass
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


# Source origin is intentionally separate from content language. An
# international source can publish Korean content, and a Korean source can
# report a global event.
SOURCE_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "official_ai_blogs": {"regions": ["international"], "languages": ["en"], "information_types": ["official_update", "research"], "implemented": True, "requires_feed_urls": True},
    "hackernews": {"regions": ["international"], "languages": ["en"], "information_types": ["community", "technology"], "implemented": True},
    "github": {"regions": ["international"], "languages": ["multilingual"], "information_types": ["open_source", "repository"], "implemented": True},
    "youtube": {"regions": ["domestic", "international"], "languages": ["ko", "en", "multilingual"], "information_types": ["video", "creator"], "implemented": True, "requires_env": ["YOUTUBE_API_KEY"]},
    "rss": {"regions": ["domestic", "international"], "languages": ["multilingual"], "information_types": ["news", "official_update"], "implemented": True, "requires_feed_urls": True},
    "company_newsroom": {"regions": ["domestic", "international"], "languages": ["multilingual"], "information_types": ["official_update"], "implemented": True, "requires_feed_urls": True},
    # Parsers are covered by fixtures, but these feeds must not enter a user
    # feed until reuse/storage and AI-processing terms have been confirmed.
    "geeknews": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["community", "technology", "startup"], "implemented": True, "requires_feed_urls": True, "distribution_status": "permission_review"},
    "kisa_press": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["official_announcement"], "implemented": True, "requires_feed_urls": True, "distribution_status": "permission_review"},
    "kisa_research": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["research_report"], "implemented": True, "requires_feed_urls": True, "distribution_status": "permission_review"},
    "producthunt": {"regions": ["international"], "languages": ["en"], "information_types": ["product_launch"], "implemented": False},
    "reddit": {"regions": ["international"], "languages": ["multilingual"], "information_types": ["community"], "implemented": False},
    "naver_news": {"regions": ["domestic"], "languages": ["ko"], "information_types": ["news", "industry"], "implemented": False, "requires_auth": "NAVER API credentials"},
    "arxiv": {"regions": ["international"], "languages": ["en"], "information_types": ["research"], "implemented": False},
}


def source_availability(source_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    capability = SOURCE_CAPABILITIES.get(source_id, {})
    if not capability.get("implemented", False):
        return {"available": False, "reason": "아직 연결 준비 중이에요.", "capabilities": capability}
    if capability.get("distribution_status") == "permission_review":
        return {"available": False, "reason": "이용 조건 확인이 끝나기 전까지 사용자 피드에 공개하지 않아요.", "capabilities": capability}
    missing_env = [name for name in capability.get("requires_env", []) if not os.environ.get(name, "").strip()]
    if missing_env:
        return {"available": False, "reason": f"{' / '.join(missing_env)} 설정이 필요해요.", "capabilities": capability}
    if capability.get("requires_feed_urls") and not (config or {}).get("feed_urls"):
        return {"available": False, "reason": "RSS 주소를 먼저 추가해주세요.", "capabilities": capability}
    return {"available": True, "reason": "사용할 수 있어요.", "capabilities": capability}


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
    "geeknews": SourceMetadata(
        source_id="geeknews", display_name="GeekNews", categories=["DEVELOPER_TECH", "STARTUP_PRODUCT"],
        default_limit=6, trust_score=0.6, freshness_weight=0.7, community_weight=0.8,
        enabled_by_default=False, description="Korean developer, technology, and startup community links.",
    ),
    "kisa_press": SourceMetadata(
        source_id="kisa_press", display_name="KISA 보도자료", categories=["SECURITY_PRIVACY", "DOMESTIC_INDUSTRY"],
        default_limit=5, trust_score=0.9, freshness_weight=0.8, community_weight=0.1,
        enabled_by_default=False, description="Korea Internet & Security Agency official press releases.",
    ),
    "kisa_research": SourceMetadata(
        source_id="kisa_research", display_name="KISA 연구보고서", categories=["SECURITY_PRIVACY", "RESEARCH"],
        default_limit=5, trust_score=0.9, freshness_weight=0.6, community_weight=0.1,
        enabled_by_default=False, description="Korea Internet & Security Agency research reports.",
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
        item["selection_mode"] = config.get("selection_mode", "auto")
        item["priority"] = int(config.get("priority", 50))
        item["config_json"] = config.get("config_json", {})
        availability = source_availability(source_id, item["config_json"])
        item["available"] = availability["available"]
        item["availability_reason"] = availability["reason"]
        item["capabilities"] = availability["capabilities"]
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

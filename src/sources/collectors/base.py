import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class SourceQuery:
    source: str
    query: str
    params: Dict[str, Any] = field(default_factory=dict)
    route_id: Optional[int] = None
    route_date: Optional[str] = None
    category: str = ""
    reason: str = ""


@dataclass
class CollectedItem:
    source: str
    source_item_id: str
    url: str
    title: str
    summary: str = ""
    author: str = ""
    published_at: Optional[str] = None
    metrics_json: Dict[str, Any] = field(default_factory=dict)
    raw_json: Dict[str, Any] = field(default_factory=dict)
    collected_at: str = field(default_factory=lambda: datetime.utcnow().replace(microsecond=0).isoformat())
    dedupe_key: str = ""
    route_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if not data["published_at"]:
            data["published_at"] = data["collected_at"]
        if not data["source_item_id"]:
            data["source_item_id"] = build_source_item_id(data["source"], data["url"], data["title"], data["published_at"])
        if not data["dedupe_key"]:
            data["dedupe_key"] = build_dedupe_key(data)
        return data


@dataclass
class CollectorResult:
    source: str
    items: List[CollectedItem] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    attempted: bool = True
    implemented: bool = True

    def item_dicts(self) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in self.items]


class BaseCollector:
    source_id = ""
    implemented = True

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        raise NotImplementedError


class NoOpCollector(BaseCollector):
    implemented = False

    def __init__(self, source_id: str):
        self.source_id = source_id

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        return CollectorResult(
            source=self.source_id,
            items=[],
            warnings=[f"Collector for {self.source_id} is not implemented."],
            implemented=False,
        )


def build_source_item_id(source: str, url: str, title: str, published_at: str = "") -> str:
    if url:
        raw = f"{source}:url:{normalize_text(url)}"
    else:
        raw = f"{source}:title:{normalize_text(title)}:{str(published_at)[:10]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_dedupe_key(item: Dict[str, Any]) -> str:
    source = normalize_text(item.get("source", ""))
    source_item_id = normalize_text(item.get("source_item_id", ""))
    if source_item_id:
        raw = f"{source}:id:{source_item_id}"
    elif item.get("url"):
        raw = f"{source}:url:{normalize_text(item.get('url', ''))}"
    else:
        raw = f"{source}:title:{normalize_text(item.get('title', ''))}:{str(item.get('published_at', ''))[:10]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ContextItem:
    connector_type: str
    item_id: str
    title: str
    text: str
    url: str = ""
    path: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata_json: Dict[str, Any] = field(default_factory=dict)

    def to_store_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["text_snippet"] = self.text[:1000]
        data.pop("text", None)
        return data


@dataclass
class ConnectorResult:
    connector_type: str
    items: List[ContextItem] = field(default_factory=list)
    keywords: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    synced_at: str = field(default_factory=lambda: datetime.utcnow().replace(microsecond=0).isoformat())


class BaseContextConnector:
    connector_type = ""

    def sync(self, config: Dict[str, Any], limit: int = 100) -> ConnectorResult:
        raise NotImplementedError

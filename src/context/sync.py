from typing import Any, Dict, List, Optional

from src.context.connectors.browser import BrowserHistoryConnector
from src.context.connectors.local_files import LocalFilesConnector
from src.storage.sqlite_store import SQLiteStore


CONNECTOR_REGISTRY = {
    "browser_history": BrowserHistoryConnector,
    "local_files": LocalFilesConnector,
}


def sync_enabled_connectors(
    store: SQLiteStore,
    connector_types: Optional[List[str]] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    connectors = store.get_connectors()
    selected = []
    for connector in connectors:
        if connector_types and connector["connector_type"] not in connector_types:
            continue
        if connector["enabled"]:
            selected.append(connector)

    summaries = []
    for connector in selected:
        summaries.append(sync_connector(store, connector["connector_type"], connector.get("config_json", {}), limit=limit))

    return {
        "synced_connectors": [item["connector_type"] for item in summaries],
        "item_count": sum(item["item_count"] for item in summaries),
        "keyword_count": sum(item["keyword_count"] for item in summaries),
        "errors": {item["connector_type"]: item["errors"] for item in summaries if item["errors"]},
        "warnings": {item["connector_type"]: item["warnings"] for item in summaries if item["warnings"]},
        "updated_keywords": [keyword for item in summaries for keyword in item["updated_keywords"]],
        "runs": summaries,
    }


def sync_connector(store: SQLiteStore, connector_type: str, config: Dict[str, Any], limit: int = 100) -> Dict[str, Any]:
    run_id = store.create_context_sync_run(connector_type)
    connector_class = CONNECTOR_REGISTRY.get(connector_type)
    if not connector_class:
        message = f"Connector is not implemented: {connector_type}"
        store.fail_context_sync_run(run_id, message, {"connector_type": connector_type})
        store.update_connector_sync_status(connector_type, "not_implemented", message)
        return {
            "connector_type": connector_type,
            "item_count": 0,
            "keyword_count": 0,
            "errors": [message],
            "warnings": [],
            "updated_keywords": [],
        }

    try:
        result = connector_class().sync(config or {}, limit=limit)
        item_ids = [store.upsert_context_item(item.to_store_dict()) for item in result.items]
        updated = apply_keywords_to_interest_graph(store, connector_type, result.keywords, result.items)
        summary = {
            "connector_type": connector_type,
            "item_ids": item_ids[:20],
            "errors": result.errors,
            "warnings": result.warnings,
            "updated_keywords": updated,
        }
        status = "completed" if not result.errors else "completed_with_errors"
        store.complete_context_sync_run(run_id, len(result.items), len(result.keywords), summary)
        store.update_connector_sync_status(connector_type, status, "; ".join(result.errors) if result.errors else None)
        return {
            "connector_type": connector_type,
            "item_count": len(result.items),
            "keyword_count": len(result.keywords),
            "errors": result.errors,
            "warnings": result.warnings,
            "updated_keywords": updated,
        }
    except Exception as exc:
        message = str(exc)
        store.fail_context_sync_run(run_id, message, {"connector_type": connector_type})
        store.update_connector_sync_status(connector_type, "failed", message)
        return {
            "connector_type": connector_type,
            "item_count": 0,
            "keyword_count": 0,
            "errors": [message],
            "warnings": [],
            "updated_keywords": [],
        }


def apply_keywords_to_interest_graph(store: SQLiteStore, connector_type: str, keywords: List[Dict[str, Any]], items) -> List[str]:
    if not store.get_settings().get("auto_expand_interests", False):
        return []
    updated = []
    evidence_items = []
    for item in list(items)[:5]:
        evidence_items.append({"title": item.title[:120], "url": item.url, "path": item.path})
    for keyword in keywords[:30]:
        text = str(keyword.get("keyword", "")).strip()
        if not text:
            continue
        if store.is_interest_blocked(text):
            continue
        weight = min(2.0, max(0.1, float(keyword.get("score", 0.0))))
        store.adjust_interest_weight(
            text,
            delta=weight,
            category="personal_context",
            source=connector_type,
            evidence={"connector_type": connector_type, "items": evidence_items, "keyword": keyword},
            maximum=10.0,
        )
        updated.append(text)
    return updated


class ContextSync:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def run_once(self, connector_types: Optional[List[str]] = None, limit: int = 100):
        return sync_enabled_connectors(self.store, connector_types=connector_types, limit=limit)

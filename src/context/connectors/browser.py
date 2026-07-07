import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.context.connectors.base import BaseContextConnector, ConnectorResult, ContextItem
from src.context.keyword_extraction import extract_keywords, merge_keyword_scores


class BrowserHistoryConnector(BaseContextConnector):
    connector_type = "browser_history"

    def sync(self, config: Dict[str, Any], limit: int = 100) -> ConnectorResult:
        errors: List[str] = []
        warnings: List[str] = []
        try:
            rows = config.get("sample_items")
            if rows is None:
                rows = self._read_browser_rows(config, limit)
            items = self._items_from_rows(rows, config, limit)
            keywords = merge_keyword_scores([extract_keywords(f"{item.title} {item.text}", 10) for item in items])
            return ConnectorResult(self.connector_type, items=items, keywords=keywords, errors=errors, warnings=warnings)
        except Exception as exc:
            errors.append(str(exc))
            return ConnectorResult(self.connector_type, errors=errors, warnings=warnings)

    def _items_from_rows(self, rows: Iterable[Dict[str, Any]], config: Dict[str, Any], limit: int) -> List[ContextItem]:
        exclude_domains = config.get("exclude_domains", ["localhost", "127.0.0.1"]) or []
        include_domains = config.get("include_domains", []) or []
        items = []
        for row in rows:
            title = str(row.get("title") or "")
            url = str(row.get("url") or "")
            if include_domains and not any(domain in url for domain in include_domains):
                continue
            if any(domain in url for domain in exclude_domains):
                continue
            item_id = str(row.get("id") or row.get("item_id") or url or title)
            updated_at = row.get("last_visit_time") or row.get("updated_at")
            items.append(
                ContextItem(
                    connector_type=self.connector_type,
                    item_id=item_id,
                    title=title[:300],
                    text=f"{title} {url}",
                    url=url,
                    updated_at=str(updated_at) if updated_at else None,
                    metadata_json={"source": "browser_history"},
                )
            )
            if len(items) >= limit:
                break
        return items

    def _read_browser_rows(self, config: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        history_path = config.get("history_path") or self._default_history_path()
        if not history_path:
            return []
        source = Path(history_path)
        if not source.exists():
            return []
        days = int(config.get("days", 7))
        since = datetime.utcnow() - timedelta(days=days)
        chrome_epoch = datetime(1601, 1, 1)
        since_chrome = int((since - chrome_epoch).total_seconds() * 1_000_000)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            shutil.copy2(source, tmp_path)
            conn = sqlite3.connect(tmp_path)
            rows = conn.execute(
                """
                SELECT id, title, url, last_visit_time
                FROM urls
                WHERE last_visit_time >= ?
                ORDER BY last_visit_time DESC
                LIMIT ?
                """,
                (since_chrome, limit),
            ).fetchall()
            conn.close()
            return [{"id": row[0], "title": row[1], "url": row[2], "last_visit_time": row[3]} for row in rows]
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _default_history_path(self) -> str:
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            return ""
        candidates = [
            Path(local) / "Google" / "Chrome" / "User Data" / "Default" / "History",
            Path(local) / "Microsoft" / "Edge" / "User Data" / "Default" / "History",
        ]
        for path in candidates:
            if path.exists():
                return str(path)
        return ""


BrowserConnector = BrowserHistoryConnector

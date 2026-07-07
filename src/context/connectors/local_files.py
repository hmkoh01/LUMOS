from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from src.context.connectors.base import BaseContextConnector, ConnectorResult, ContextItem
from src.context.keyword_extraction import extract_keywords, merge_keyword_scores


class LocalFilesConnector(BaseContextConnector):
    connector_type = "local_files"
    DEFAULT_EXTENSIONS = [".txt", ".md", ".markdown", ".csv"]

    def sync(self, config: Dict[str, Any], limit: int = 100) -> ConnectorResult:
        errors: List[str] = []
        warnings: List[str] = []
        folders = [Path(folder) for folder in config.get("folders", []) or [] if str(folder).strip()]
        if not folders:
            return ConnectorResult(self.connector_type, warnings=["No folders configured for local_files."])

        extensions = set(config.get("extensions") or self.DEFAULT_EXTENSIONS)
        max_size = float(config.get("max_file_size_mb", 5)) * 1024 * 1024
        days = int(config.get("days", 30))
        since = datetime.utcnow() - timedelta(days=days)
        files = []
        for folder in folders:
            if not folder.exists() or not folder.is_dir():
                warnings.append(f"Folder not found: {folder}")
                continue
            for path in folder.rglob("*"):
                try:
                    if not path.is_file() or path.suffix.lower() not in extensions:
                        continue
                    stat = path.stat()
                    if stat.st_size > max_size or datetime.utcfromtimestamp(stat.st_mtime) < since:
                        continue
                    files.append((path, stat.st_mtime))
                except Exception as exc:
                    errors.append(f"{path}: {exc}")
        files = sorted(files, key=lambda item: item[1], reverse=True)[:limit]
        items = []
        for path, mtime in files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                items.append(
                    ContextItem(
                        connector_type=self.connector_type,
                        item_id=str(path.resolve()),
                        title=path.name,
                        text=text[:4000],
                        path=str(path),
                        updated_at=datetime.utcfromtimestamp(mtime).isoformat(),
                        metadata_json={"extension": path.suffix.lower(), "size": path.stat().st_size},
                    )
                )
            except Exception as exc:
                errors.append(f"{path}: {exc}")
        keywords = merge_keyword_scores([extract_keywords(f"{item.title} {item.text}", 10) for item in items])
        return ConnectorResult(self.connector_type, items=items, keywords=keywords, errors=errors, warnings=warnings)

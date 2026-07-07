import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery


class GitHubCollector(BaseCollector):
    source_id = "github"
    SEARCH_URL = "https://api.github.com/search/repositories"

    def __init__(self, fetch_json: Optional[Callable[[str, float, Dict[str, str]], Any]] = None, timeout: float = 8.0):
        self.fetch_json = fetch_json or self._fetch_json
        self.timeout = timeout

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        items: List[CollectedItem] = []
        warnings: List[str] = []
        seen = set()
        for query in queries:
            if len(items) >= limit:
                break
            try:
                payload = self.fetch_json(self._search_url(query, limit), self.timeout, self._headers())
            except Exception as exc:
                warnings.append(f"{query.query}: {exc}")
                continue
            if isinstance(payload, dict) and payload.get("message") and "rate limit" in str(payload.get("message")).lower():
                warnings.append(f"rate limit: {payload.get('message')}")
                continue
            for repo in (payload or {}).get("items", []):
                item = self._normalize_repo(repo, query.route_id)
                if not item or item.source_item_id in seen:
                    continue
                seen.add(item.source_item_id)
                items.append(item)
                if len(items) >= limit:
                    break
        return CollectorResult(source=self.source_id, items=items[:limit], warnings=warnings)

    def _search_url(self, query: SourceQuery, limit: int) -> str:
        params = query.params or {}
        min_stars = int(params.get("min_stars", 20))
        sort = params.get("sort", "updated")
        pushed_after = params.get("pushed_after") or (datetime.utcnow() - timedelta(days=365)).date().isoformat()
        q = str(query.query or "").strip()
        if "stars:" not in q:
            q = f"{q} stars:>{min_stars}"
        if "pushed:" not in q:
            q = f"{q} pushed:>{pushed_after}"
        encoded = urllib.parse.urlencode({"q": q, "sort": sort, "order": "desc", "per_page": max(1, min(limit, 20))})
        return f"{self.SEARCH_URL}?{encoded}"

    def _normalize_repo(self, repo: Dict[str, Any], route_id: Optional[int]) -> Optional[CollectedItem]:
        full_name = repo.get("full_name") or ""
        if not full_name:
            return None
        owner = (repo.get("owner") or {}).get("login") or full_name.split("/", 1)[0]
        return CollectedItem(
            source=self.source_id,
            source_item_id=str(repo.get("id") or full_name),
            url=repo.get("html_url") or "",
            title=full_name[:300],
            summary=(repo.get("description") or "")[:500],
            author=owner,
            published_at=repo.get("pushed_at") or repo.get("updated_at"),
            metrics_json={
                "stars": int(repo.get("stargazers_count") or 0),
                "forks": int(repo.get("forks_count") or 0),
                "language": repo.get("language"),
                "open_issues": int(repo.get("open_issues_count") or 0),
            },
            raw_json={
                "full_name": full_name,
                "default_branch": repo.get("default_branch"),
                "archived": bool(repo.get("archived")),
                "pushed_at": repo.get("pushed_at"),
                "updated_at": repo.get("updated_at"),
            },
            route_id=route_id,
        )

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "LUMOS/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _fetch_json(self, url: str, timeout: float, headers: Dict[str, str]):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            body = exc.read(200_000).decode("utf-8", errors="replace")
            try:
                payload = json.loads(body)
            except Exception:
                payload = {"message": body or str(exc)}
            if exc.code in {403, 429}:
                return {"message": payload.get("message", "GitHub rate limit or access denied")}
            raise

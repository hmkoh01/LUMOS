import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List

from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery


class MockCollector(BaseCollector):
    source_id = "mock"

    def collect(self, queries: List[Any], limit: int = 5):
        if queries and isinstance(queries[0], dict):
            return self.collect_routes(queries)

        items = []
        safe_limit = max(1, min(int(limit or 5), 5))
        for query_index, query in enumerate(queries[:2]):
            for item_index in range(1, min(safe_limit, 2) + 1):
                item = self._build_item_from_query(query, query_index, item_index)
                items.append(CollectedItem(**item))
        source = queries[0].source if queries else "mock"
        return CollectorResult(source=source, items=items)

    def collect_routes(self, planned_routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items = []
        for route in planned_routes:
            source = route["source"]
            limit = max(1, min(int(route.get("collection_limit", 5)), 5))
            for query_index, query in enumerate(route.get("queries", [])[:2]):
                source_query = SourceQuery(
                    source=source,
                    query=query["query"],
                    params=query.get("params", {}),
                    route_id=route.get("route_id"),
                    route_date=route.get("route_date"),
                    category=route.get("category", ""),
                    reason=route.get("reason", ""),
                )
                for item_index in range(1, min(limit, 2) + 1):
                    items.append(self._build_item_from_query(source_query, query_index, item_index))
        return items

    def _build_item_from_query(self, query: SourceQuery, query_index: int, item_index: int) -> Dict[str, Any]:
        query_text = query.query
        source = query.source
        seed = f"{query.route_date or ''}:{source}:{query_text}:{item_index}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        published_at = (datetime.utcnow() - timedelta(hours=query_index * 5 + item_index)).replace(microsecond=0).isoformat()
        metrics = self._metrics(source, digest, item_index)
        title, summary, author = self._content(source, query_text, query.category, metrics)
        return {
            "source": source,
            "source_item_id": digest,
            "url": f"https://example.com/{source}/{digest}",
            "title": title,
            "summary": summary,
            "author": author,
            "published_at": published_at,
            "metrics_json": metrics,
            "raw_json": {
                "mock": True,
                "query": {"query": query.query, "params": query.params},
                "route": {
                    "category": query.category,
                    "reason": query.reason,
                },
            },
            "collected_at": datetime.utcnow().replace(microsecond=0).isoformat(),
            "route_id": query.route_id,
        }

    def _metrics(self, source: str, digest: str, item_index: int) -> Dict[str, Any]:
        base = int(digest[:4], 16) % 100
        if source == "github":
            return {"stars": 80 + base, "forks": 5 + item_index, "recent_commits": 3 + item_index}
        if source == "hackernews":
            return {"points": 40 + base, "comments": 10 + item_index * 3}
        if source == "producthunt":
            return {"upvotes": 60 + base, "comments": 8 + item_index}
        if source == "reddit":
            return {"upvotes": 30 + base, "comments": 12 + item_index}
        if source == "youtube":
            return {"views": 1000 + base * 100, "comments": 20 + item_index}
        if source == "naver_news":
            return {"mentions": 5 + item_index, "rank": item_index}
        if source == "arxiv":
            return {"citations_proxy": 2 + item_index, "abstract_reads": 100 + base}
        return {"mentions": 10 + item_index, "score": base}

    def _content(self, source: str, query: str, category: str, metrics: Dict[str, Any]):
        if source == "github":
            return (
                f"{query} repo adds workflow automation primitives",
                f"A mock GitHub update shows growing implementation activity around {query}, with stars and recent commits indicating developer momentum.",
                "mock-github",
            )
        if source == "hackernews":
            return (
                f"Developers discuss whether {query} is becoming a practical default",
                f"A mock Hacker News discussion around {query} is accumulating points and comments, suggesting active technical debate.",
                "mock-hn",
            )
        if source == "producthunt":
            return (
                f"New {query} product launches with personalized briefing angle",
                f"A mock Product Hunt launch positions {query} as a lighter way to turn noisy information into daily action.",
                "mock-producthunt",
            )
        if source == "naver_news":
            return (
                f"국내 시장에서 {query} 관련 움직임이 확대",
                f"Mock Naver News item: {query} 관련 기업과 산업 논의가 늘며 커리어와 사업 기회 측면에서 주목받고 있습니다.",
                "mock-naver",
            )
        if source == "reddit":
            return (
                f"Community reaction: what users actually want from {query}",
                f"A mock Reddit thread highlights practical frustrations, adoption blockers, and repeated requests around {query}.",
                "mock-reddit",
            )
        if source == "official_ai_blogs":
            return (
                f"Official update points {query} toward more agentic workflows",
                f"A mock official AI blog update frames {query} as part of a shift toward background automation and user-specific context.",
                "mock-official",
            )
        if source == "arxiv":
            return (
                f"Paper trend: {query} methods become more context-aware",
                f"A mock arXiv item indicates research movement around {query}, with emphasis on personalization and retrieval.",
                "mock-arxiv",
            )
        if source == "company_newsroom":
            return (
                f"Company newsroom update references {query} strategy",
                f"A mock company update connects {query} to product roadmap, partnerships, or market positioning.",
                "mock-newsroom",
            )
        return (
            f"{query} appears in {category} source monitoring",
            f"A mock source item suggests that {query} is relevant to the selected category {category}.",
            "mock-source",
        )

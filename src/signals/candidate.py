from typing import Any, Dict, List

from src.storage.sqlite_store import SQLiteStore


class CandidateBuilder:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def create_from_source_items(
        self,
        source_items: List[Dict[str, Any]],
        interests: List[Dict[str, Any]],
        pipeline_run_id: int = None,
    ) -> List[Dict[str, Any]]:
        created = []
        keywords = [item["keyword"] for item in interests if item.get("keyword")]
        for item in source_items:
            matched = self.match_keywords(item, keywords)
            candidate_id = self.store.create_signal_candidate(
                source_item_id=item["id"],
                route_id=item.get("route_id") or 0,
                matched_keywords=matched,
                pipeline_run_id=pipeline_run_id,
                category=item.get("route_category") or item.get("category") or "",
            )
            candidate = self.store.get_candidate(candidate_id)
            if candidate:
                created.append(candidate)
        return created

    def match_keywords(self, item: Dict[str, Any], keywords: List[str]) -> List[str]:
        haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        matched = []
        for keyword in keywords:
            keyword_text = str(keyword).strip()
            if keyword_text and keyword_text.lower() in haystack:
                matched.append(keyword_text)
        return matched

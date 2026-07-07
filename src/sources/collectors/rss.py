import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Callable, Dict, List, Optional, Set

from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery, build_source_item_id


class RSSCollector(BaseCollector):
    source_id = "rss"

    def __init__(self, fetch_text: Optional[Callable[[str, float], str]] = None, timeout: float = 5.0, source_id: str = "rss"):
        self.fetch_text = fetch_text or self._fetch_text
        self.timeout = timeout
        self.source_id = source_id

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        items: List[CollectedItem] = []
        warnings = []
        feed_urls = self._feed_urls(queries)
        if not feed_urls:
            return CollectorResult(source=self.source_id, warnings=["No RSS feed URL was provided."], items=[])

        seen: Set[str] = set()
        for feed_url in feed_urls:
            if len(items) >= limit:
                break
            try:
                xml_text = self.fetch_text(feed_url, self.timeout)
                parsed = self._parse_feed(xml_text, feed_url, queries, limit - len(items), seen)
                items.extend(parsed)
            except Exception as exc:
                warnings.append(f"{feed_url}: {exc}")

        return CollectorResult(source=self.source_id, items=items[:limit], warnings=warnings)

    def _feed_urls(self, queries: List[SourceQuery]) -> List[str]:
        urls = []
        for query in queries:
            params = query.params or {}
            for key in ("feed_url", "url"):
                value = params.get(key)
                if value:
                    urls.append(str(value))
            for value in params.get("feed_urls", []) or []:
                urls.append(str(value))
            if str(query.query).startswith("http"):
                urls.append(query.query)
        return list(dict.fromkeys(urls))

    def _parse_feed(self, xml_text: str, feed_url: str, queries: List[SourceQuery], limit: int, seen: Set[str]) -> List[CollectedItem]:
        root = ET.fromstring(xml_text)
        feed_title = self._first_text(root, ["./channel/title", "./{*}title"]) or feed_url
        entries = root.findall("./channel/item") or root.findall("./{*}entry")
        query_terms = self._query_terms(queries)
        route_id = queries[0].route_id if queries else None
        category = queries[0].category if queries else ""
        matched_items = []
        fallback_items = []
        for entry in entries:
            title = self._entry_text(entry, ["title"]) or "Untitled RSS item"
            url = self._entry_link(entry)
            summary = self._clean_html(self._entry_text(entry, ["description", "summary", "content"]) or "")
            author = self._entry_text(entry, ["author", "creator"]) or feed_title
            published_at = self._parse_date(self._entry_text(entry, ["pubDate", "published", "updated"]))
            dedupe_source = url or f"{title}:{published_at}"
            if dedupe_source in seen:
                continue
            seen.add(dedupe_source)
            haystack = f"{title} {url} {summary}".lower()
            item_id = build_source_item_id(self.source_id, url, title, published_at)
            item = (
                CollectedItem(
                    source=self.source_id,
                    source_item_id=item_id,
                    url=url,
                    title=title[:300],
                    summary=summary[:500],
                    author=author[:120],
                    published_at=published_at,
                    metrics_json={"feed_title": feed_title, "category": category, "matched_query": bool(query_terms and any(term in haystack for term in query_terms))},
                    raw_json={"feed_url": feed_url, "feed_title": feed_title, "format": root.tag.split("}", 1)[-1]},
                    route_id=route_id,
                )
            )
            if query_terms and any(term in haystack for term in query_terms):
                matched_items.append(item)
            else:
                fallback_items.append(item)
            if len(matched_items) >= limit:
                break
        return (matched_items + fallback_items)[:limit]

    def _query_terms(self, queries: List[SourceQuery]) -> List[str]:
        terms = []
        for query in queries:
            if query.query and not str(query.query).startswith("http"):
                terms.append(str(query.query).lower())
            for keyword in (query.params or {}).get("keywords", []) or []:
                terms.append(str(keyword).lower())
        return list(dict.fromkeys(term for term in terms if term))

    def _fetch_text(self, url: str, timeout: float) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": "LUMOS/0.1"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(1_000_000).decode("utf-8", errors="replace")

    def _first_text(self, root: ET.Element, paths: List[str]) -> str:
        for path in paths:
            node = root.find(path)
            if node is not None and node.text:
                return node.text.strip()
        return ""

    def _entry_text(self, entry: ET.Element, names: List[str]) -> str:
        for name in names:
            for node in entry.iter():
                tag = node.tag.split("}", 1)[-1]
                if tag == name and node.text:
                    return node.text.strip()
        return ""

    def _entry_link(self, entry: ET.Element) -> str:
        link_text = self._entry_text(entry, ["link"])
        if link_text:
            return link_text
        for node in entry.iter():
            tag = node.tag.split("}", 1)[-1]
            if tag == "link" and node.attrib.get("href"):
                return node.attrib["href"]
        return ""

    def _parse_date(self, value: str) -> str:
        if not value:
            return datetime.utcnow().replace(microsecond=0).isoformat()
        try:
            return parsedate_to_datetime(value).replace(tzinfo=None).isoformat()
        except Exception:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None).isoformat()
            except Exception:
                return datetime.utcnow().replace(microsecond=0).isoformat()

    def _clean_html(self, value: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()

import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Dict, List, Optional, Set

from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery, build_source_item_id
from src.context.interest_matching import matches_interest
from src.sources.content_rights import classify_opportunity_status


class RSSCollector(BaseCollector):
    source_id = "rss"
    # Several official feeds exceed 1 MiB. Reading only the first MiB cuts
    # XML in the middle of an entry and makes the whole source look malformed.
    MAX_FEED_BYTES = 8 * 1024 * 1024

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
        params = queries[0].params if queries else {}
        content_policy = dict(params.get("content_policy") or {})
        content_filter = dict(params.get("content_filter") or {})
        source_context = {
            "feed_url": feed_url,
            "feed_title": feed_title,
            "publisher": feed_title,
            "language": params.get("language") or "unknown",
            "source_region": params.get("source_region") or params.get("region") or "unknown",
            "content_region": params.get("content_region") or "unknown",
            "content_type": params.get("content_type") or category or "unknown",
            "usage_status": params.get("usage_status") or "unknown",
        }
        matched_items = []
        fallback_items = []
        for entry in entries:
            title = self._entry_text(entry, ["title"]) or "Untitled RSS item"
            url = self._entry_link(entry)
            opportunity_status = classify_opportunity_status(title)
            if params.get("opportunity_only") and opportunity_status == "not_new_opportunity":
                continue
            feed_excerpt = self._clean_html(self._entry_text(entry, ["description", "summary", "content"]) or "")
            # RSS availability is not a licence to retain article excerpts or
            # send them to an LLM. Sources can opt into metadata-only
            # collection while still using title/URL matching and provenance.
            summary = feed_excerpt if content_policy.get("excerpt_storage") == "approved" else ""
            author = self._entry_text(entry, ["author", "creator"]) or feed_title
            published_at = self._parse_date(self._entry_text(entry, ["pubDate", "published", "updated", "date"]))
            dedupe_source = url or f"{title}:{published_at}"
            if dedupe_source in seen:
                continue
            seen.add(dedupe_source)
            observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            # Do not inspect or persist publisher-owned excerpts merely to
            # classify a metadata-only feed.  A source-specific title/URL
            # filter is enough to keep broad feeds such as blog.google from
            # flooding an AI-trend route with unrelated posts.
            classification_text = f"{title} {url}"
            interest_match = bool(query_terms and any(matches_interest(classification_text, term) for term in query_terms))
            type_match = self._matches_content_filter(classification_text, content_filter)
            allow_type_match = category == "AI_TREND" and bool(content_filter.get("allow_category_match"))
            if content_filter and not type_match:
                continue
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
                    metrics_json={
                        "feed_title": feed_title, "category": category,
                        "matched_query": interest_match,
                        "matched_information_type": type_match,
                        "opportunity_status": opportunity_status,
                    },
                    # An RSS timestamp is the feed publisher's publication
                    # time. It is not inferred to be the underlying event date.
                    raw_json={
                        **source_context,
                        "format": root.tag.split("}", 1)[-1],
                        "event_occurred_at": None,
                        "source_published_at": published_at,
                        # Collection time is a LUMOS observation time, never
                        # evidence that the underlying event happened then.
                        "first_observed_at": observed_at,
                        "source_role": params.get("source_role") or "primary",
                        "verification_status": params.get("verification_status") or "unverified",
                        "rights_evidence_url": params.get("rights_evidence_url") or None,
                        "requires_post_rights": bool(params.get("requires_post_rights")),
                        "content_policy": content_policy,
                    },
                    collected_at=observed_at,
                    route_id=route_id,
                )
            )
            if interest_match or (allow_type_match and type_match):
                matched_items.append(item)
            else:
                fallback_items.append(item)
            if len(matched_items) >= limit:
                break
        return (matched_items if query_terms else fallback_items)[:limit]

    @staticmethod
    def _matches_content_filter(text: str, content_filter: Dict[str, object]) -> bool:
        """Apply transparent title/URL-only source-type filters.

        ``any_terms`` is intentionally conservative: it expresses what the
        source is allowed to contribute to this route, not a broad semantic
        classifier.  Empty filters mean no type-specific restriction.
        """
        if not content_filter:
            return True
        normalized = " ".join(str(text or "").casefold().split())
        excludes = [str(term).casefold() for term in content_filter.get("exclude_terms", [])]
        if any(term and term in normalized for term in excludes):
            return False
        all_terms = [str(term).casefold() for term in content_filter.get("all_terms", [])]
        if all_terms and not all(term in normalized for term in all_terms):
            return False
        any_terms = [str(term).casefold() for term in content_filter.get("any_terms", [])]
        return not any_terms or any(term in normalized for term in any_terms)

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
            payload = response.read(self.MAX_FEED_BYTES + 1)
            content_type = response.headers.get("Content-Type", "")
        if len(payload) > self.MAX_FEED_BYTES:
            raise ValueError(f"RSS feed exceeds {self.MAX_FEED_BYTES // (1024 * 1024)} MiB")
        return self._decode_payload(payload, content_type)

    @staticmethod
    def _decode_payload(payload: bytes, content_type: str = "") -> str:
        """Respect declared HTTP/XML encodings before falling back to UTF-8.

        Government RSS feeds are commonly served in legacy Korean encodings;
        blindly replacing invalid UTF-8 bytes destroys titles and prevents
        relevance matching.
        """
        candidates = []
        header = re.search(r"charset\s*=\s*['\"]?([^;'\"\s]+)", content_type or "", re.I)
        if header:
            candidates.append(header.group(1))
        declaration = re.search(br"<\?xml[^>]+encoding=[\"']([^\"']+)", payload[:256], re.I)
        if declaration:
            candidates.append(declaration.group(1).decode("ascii", errors="ignore"))
        candidates.extend(["utf-8", "euc-kr", "cp949"])
        for encoding in dict.fromkeys(candidate for candidate in candidates if candidate):
            try:
                return payload.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
        return payload.decode("utf-8", errors="replace")

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

    def _parse_date(self, value: str) -> Optional[str]:
        if not value:
            return None
        try:
            return parsedate_to_datetime(value).replace(tzinfo=None).isoformat()
        except Exception:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None).isoformat()
            except Exception:
                return None

    def _clean_html(self, value: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()

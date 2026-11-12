"""Collector for data.go.kr service 15113297, MSS business announcements.

The public catalogue confirms XML and the high-level fields, but its detailed
issued endpoint/schema is available only after an application.  Therefore this
collector accepts the endpoint and authentication parameter name from the
approved source configuration; it never guesses an endpoint or calls a service
without a key.  The parser deliberately preserves missing fields as missing.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional

from src.context.interest_matching import matches_interest
from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery, build_source_item_id


class MSSBizInfoCollector(BaseCollector):
    source_id = "mss_bizinfo"
    SERVICE_ID = "15113297"
    # The public catalogue documents this service as an XML list containing
    # announcement title/author/attachment information.  It does *not*
    # publish a complete field-level model before the issued OpenAPI guide is
    # available.  Keep aliases as compatibility/observability only: a field
    # is never manufactured when an issued response does not contain it.
    DIAGNOSTIC_FIELDS = {
        "announcement_id": ("pblancId", "nttId", "noticeId", "id"),
        "title": ("title", "pblancNm", "pblancTitle", "nttSj", "subject"),
        "published_at": ("regDate", "regDt", "pblancDate", "pblancDt", "frstRegistPnttm"),
        "application_start_at": ("applyStartDate", "rceptBeginDe", "reqstBeginDe"),
        "application_end_at": ("applyEndDate", "rceptEndDe", "reqstEndDe"),
        "support_target": ("supportTarget", "sportTrget", "trget", "target"),
        "source_url": ("url", "detailUrl", "pblancUrl", "link"),
    }

    def __init__(self, fetch_text: Optional[Callable[[str, float, Dict[str, str]], str]] = None, timeout: float = 8.0):
        self.fetch_text = fetch_text or self._fetch_text
        self.timeout = timeout

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        config = self._config(queries)
        api_key = os.environ.get("MSS_BIZINFO_API_KEY", "").strip()
        endpoint = str(config.get("api_url") or os.environ.get("MSS_BIZINFO_API_URL", "")).strip()
        if not api_key:
            return CollectorResult(source=self.source_id, errors=["MSS_BIZINFO_API_KEY is required; no request was made."], items=[])
        if not endpoint:
            return CollectorResult(source=self.source_id, errors=["MSS_BIZINFO_API_URL from the issued API guide is required; no request was made."], items=[])

        query = queries[0] if queries else SourceQuery(source=self.source_id, query="")
        try:
            xml_text = self.fetch_text(self._url(endpoint, api_key, config), self.timeout, {"Accept": "application/xml", "User-Agent": "LUMOS/0.1"})
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            return CollectorResult(source=self.source_id, errors=[f"invalid XML response: {exc}"], items=[])
        except Exception as exc:
            return CollectorResult(source=self.source_id, errors=[f"network request failed: {exc}"], items=[])

        error = self._api_error(root)
        if error:
            return CollectorResult(source=self.source_id, errors=[error], items=[])

        elements = self._item_elements(root)
        items, seen = [], set()
        for element in elements:
            item = self._normalise(element, query)
            if not item or item.source_item_id in seen:
                continue
            seen.add(item.source_item_id)
            if self._matches(item, query):
                items.append(item)
            if len(items) >= limit:
                break
        # Values are deliberately not retained here.  These bounded counts
        # are enough to diagnose issued-schema mismatches during one future
        # isolated request without leaking a public response into logs.
        presence = self._field_presence(elements)
        warnings = [f"mss_schema_{name}_present={count}" for name, count in presence.items()]
        return CollectorResult(source=self.source_id, items=items, warnings=warnings)

    @classmethod
    def _field_presence(cls, elements: Iterable[ET.Element]) -> Dict[str, int]:
        records = list(elements)
        return {
            logical_name: sum(1 for element in records if cls._value(element, aliases) is not None)
            for logical_name, aliases in cls.DIAGNOSTIC_FIELDS.items()
        }

    @staticmethod
    def _config(queries: Iterable[SourceQuery]) -> Dict[str, Any]:
        return dict(next(iter(queries), SourceQuery(source="mss_bizinfo", query="")).params or {})

    def _url(self, endpoint: str, api_key: str, config: Dict[str, Any]) -> str:
        params = dict(config.get("request_params") or {})
        params[str(config.get("auth_parameter") or "serviceKey")] = api_key
        params.setdefault("numOfRows", str(min(int(config.get("page_size") or 20), 100)))
        return f"{endpoint}{'&' if '?' in endpoint else '?'}{urllib.parse.urlencode(params)}"

    @staticmethod
    def _item_elements(root: ET.Element) -> List[ET.Element]:
        return [element for element in root.iter() if element.tag.split("}")[-1].lower() == "item"]

    @staticmethod
    def _value(element: ET.Element, names: Iterable[str]) -> Optional[str]:
        wanted = {name.casefold() for name in names}
        for child in element.iter():
            if child.tag.split("}")[-1].casefold() in wanted and child.text and child.text.strip():
                return child.text.strip()
        return None

    def _normalise(self, element: ET.Element, query: SourceQuery) -> Optional[CollectedItem]:
        title = self._value(element, ("title", "pblancNm", "pblancTitle", "nttSj", "subject"))
        if not title:
            return None
        announcement_id = self._value(element, ("pblancId", "nttId", "noticeId", "id"))
        url = self._value(element, ("url", "detailUrl", "pblancUrl", "link")) or ""
        published = self._date(self._value(element, ("regDate", "regDt", "pblancDate", "pblancDt", "frstRegistPnttm")))
        modified = self._date(self._value(element, ("updDate", "updtDt", "lastModDate", "lastUpdDt")))
        start = self._date(self._value(element, ("applyStartDate", "rceptBeginDe", "reqstBeginDe")))
        end = self._date(self._value(element, ("applyEndDate", "rceptEndDe", "reqstEndDe")))
        target = self._value(element, ("supportTarget", "sportTrget", "trget", "target"))
        keywords = self._value(element, ("keywords", "keyword", "hashTag", "tags"))
        organisation = self._value(element, ("writer", "registerNm", "insttNm", "agency", "orgNm", "deptNm"))
        source_id = announcement_id or build_source_item_id(self.source_id, url, title, published or "")
        return CollectedItem(
            source=self.source_id, source_item_id=source_id, url=url, title=title[:300], summary="",
            author=(organisation or "")[:120], published_at=published,
            metrics_json={
                "content_kind": "startup_program_announcement", "announcement_id": announcement_id,
                "announcement_published_at": published, "announcement_modified_at": modified,
                "application_start_at": start, "application_end_at": end,
                "keywords": keywords or "", "support_target": target or "",
            },
            raw_json={
                "service_id": self.SERVICE_ID, "publisher": organisation, "announcement_id": announcement_id,
                "published_at": published, "modified_at": modified, "application_start_at": start,
                "application_end_at": end, "support_target": target, "keywords": keywords,
            }, route_id=query.route_id,
        )

    @staticmethod
    def _date(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        value = value.strip()
        for pattern in ("%Y-%m-%d", "%Y.%m.%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value, pattern).isoformat()
            except ValueError:
                pass
        return None

    @staticmethod
    def _api_error(root: ET.Element) -> Optional[str]:
        code = next((node.text.strip() for node in root.iter() if node.tag.split("}")[-1].casefold() in {"resultcode", "returnreasoncode", "code"} and node.text), "")
        message = next((node.text.strip() for node in root.iter() if node.tag.split("}")[-1].casefold() in {"resultmsg", "returnauthmsg", "message"} and node.text), "")
        if code and code not in {"00", "000", "0", "normal_service"}:
            return f"API error {code}: {message or 'unspecified error'}"
        return None

    @staticmethod
    def _matches(item: CollectedItem, query: SourceQuery) -> bool:
        interest = str((query.params or {}).get("raw_interest") or query.query or "").strip()
        if not interest:
            return True
        metadata = item.metrics_json
        haystack = " ".join((item.title, item.author, str(metadata.get("keywords", "")), str(metadata.get("support_target", "")))).casefold()
        return matches_interest(haystack, interest)

    @staticmethod
    def _fetch_text(url: str, timeout: float, headers: Dict[str, str]) -> str:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(1_000_000).decode("utf-8", errors="replace")

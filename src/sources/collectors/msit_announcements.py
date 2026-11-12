"""Official MSIT business-announcement API (data.go.kr service 15074634)."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.context.interest_matching import matches_interest
from src.sources.content_rights import classify_opportunity_status
from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery, build_source_item_id


class MSITAnnouncementCollector(BaseCollector):
    source_id = "msit_announcements"
    SERVICE_ID = "15074634"
    ENDPOINT = "https://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList"
    MAX_PAGES = 3
    MAX_PAGE_SIZE = 20

    def __init__(self, fetch_json: Optional[Callable[[str, float, Dict[str, str]], Any]] = None, timeout: float = 8.0):
        self.fetch_json = fetch_json or self._fetch_json
        self.timeout = timeout

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        key = os.environ.get("MSIT_ANNOUNCEMENT_API_KEY", "").strip()
        if not key:
            return CollectorResult(source=self.source_id, errors=["MSIT_ANNOUNCEMENT_API_KEY is required; no request was made."], items=[])
        query = queries[0] if queries else SourceQuery(source=self.source_id, query="")
        params = query.params or {}
        pages = max(1, min(int(params.get("max_pages") or 1), self.MAX_PAGES))
        page_size = max(1, min(int(params.get("page_size") or limit or 1), self.MAX_PAGE_SIZE))
        records = []
        page_diagnostics = []
        for page_no in range(1, pages + 1):
            try:
                payload = self.fetch_json(self._url(key, page_size, page_no), self.timeout, {"Accept": "application/json", "User-Agent": "LUMOS/0.1"})
            except Exception as exc:
                return CollectorResult(source=self.source_id, errors=[f"network request failed on page {page_no}: {exc}"], items=[])
            error = self._api_error(payload)
            if error:
                return CollectorResult(source=self.source_id, errors=[error], items=[])
            page_records = self._records(payload)
            records.extend(page_records)
            page_diagnostics.append(self._page_diagnostics(payload, page_no, page_size, len(page_records)))
            # This API does not document a sort order. Never treat an old
            # date as an end-of-feed marker; only an empty page stops early.
            if not page_records:
                break

        items, seen = [], set()
        dated_records = interest_matched = normalised_records = 0
        missing_press_dates = invalid_press_dates = 0
        raw_ids = []
        for record in records:
            press_date = record.get("pressDt")
            if not str(press_date or "").strip():
                missing_press_dates += 1
            elif self._date(press_date) is None:
                invalid_press_dates += 1
            else:
                dated_records += 1
            item = self._normalise(record, query)
            if not item:
                continue
            normalised_records += 1
            raw_ids.append(item.source_item_id)
            if item.source_item_id in seen or not self._matches(item, query):
                continue
            interest_matched += 1
            seen.add(item.source_item_id)
            items.append(item)
        warnings = [
            f"msit_pages_requested={pages}", f"msit_records_received={len(records)}",
            f"msit_normalised_records={normalised_records}",
            f"msit_dated_records={dated_records}", f"msit_press_dt_missing={missing_press_dates}",
            f"msit_press_dt_invalid={invalid_press_dates}",
            f"msit_page_duplicates={len(raw_ids) - len(set(raw_ids))}",
            f"msit_interest_matched={interest_matched}",
        ]
        for diagnostic in page_diagnostics:
            warnings.extend(f"msit_{key}={value}" for key, value in diagnostic.items() if value is not None)
        return CollectorResult(source=self.source_id, items=items, warnings=warnings)

    def _url(self, key: str, limit: int, page_no: int = 1) -> str:
        params = {"ServiceKey": key, "pageNo": max(1, page_no), "numOfRows": max(1, min(limit, self.MAX_PAGE_SIZE)), "returnType": "json"}
        return f"{self.ENDPOINT}?{urllib.parse.urlencode(params)}"

    @staticmethod
    def _records(payload: Any) -> List[Dict[str, Any]]:
        # The documented envelope is ``response.body.items.item``.  This
        # endpoint has also returned JSON-array envelopes.  Walk only the
        # wrapper keys and select actual announcement records by ``subject``;
        # doing so is tolerant of either representation without trusting a
        # response ordering or issuing a second request.
        records: List[Dict[str, Any]] = []
        queue = [payload]
        while queue:
            current = queue.pop(0)
            if isinstance(current, list):
                queue.extend(current)
            elif isinstance(current, dict):
                if current.get("subject"):
                    records.append(current)
                else:
                    queue.extend(current[key] for key in ("response", "body", "items", "item") if key in current)
        return records

    @staticmethod
    def _page_diagnostics(payload: Any, page_no: int, requested_rows: int, received_records: int) -> Dict[str, Any]:
        """Read envelope metadata for diagnostics without trusting it for paging.

        Some responses omit or misreport these values, so collection continues
        until an empty page; the values are observability, not control flow.
        """
        response = (payload or {}).get("response") if isinstance(payload, dict) else {}
        if isinstance(response, list):
            response = next((entry for entry in response if isinstance(entry, dict) and isinstance(entry.get("body"), dict)), {})
        body = (response or {}).get("body") if isinstance(response, dict) else {}
        body = body if isinstance(body, dict) else {}
        return {
            f"page_{page_no}_requested_num_of_rows": requested_rows,
            f"page_{page_no}_response_num_of_rows": body.get("numOfRows"),
            f"page_{page_no}_total_count": body.get("totalCount"),
            f"page_{page_no}_records": received_records,
        }

    @staticmethod
    def _api_error(payload: Any) -> Optional[str]:
        queue = [payload]
        while queue:
            current = queue.pop(0)
            if isinstance(current, list):
                queue.extend(current)
                continue
            if not isinstance(current, dict):
                continue
            header = current.get("header") if isinstance(current.get("header"), dict) else current
            code = str(header.get("resultCode") or "")
            message = str(header.get("resultMsg") or "")
            if code and code not in {"00", "000", "0", "NORMAL_CODE", "NORMAL_SERVICE"}:
                return f"API error {code}: {message or 'unspecified error'}"
            queue.extend(current[key] for key in ("response", "header", "body") if key in current)
        return None

    def _normalise(self, record: Dict[str, Any], query: SourceQuery) -> Optional[CollectedItem]:
        subject = str(record.get("subject") or "").strip()
        if not subject:
            return None
        # Service 15074634 documents a posting date but not application-window
        # fields.  Selection results are not fresh opportunities, and a
        # missing window must remain unknown rather than becoming "open now".
        if classify_opportunity_status(subject) == "not_new_opportunity":
            return None
        url = str(record.get("viewUrl") or "").strip()
        published = self._date(record.get("pressDt"))
        announcement_id = self._announcement_id(record, url)
        identifier = announcement_id or build_source_item_id(self.source_id, url, subject, published or "")
        return CollectedItem(
            source=self.source_id, source_item_id=identifier, url=url, title=subject[:300], summary="",
            author=str(record.get("deptName") or "")[:120], published_at=published,
            metrics_json={
                "content_kind": "government_rnd_announcement", "announcement_id": announcement_id,
                "announcement_published_at": published,
                "application_start_at": None, "application_end_at": None,
                "application_window_status": "unknown",
            },
            raw_json={
                "service_id": self.SERVICE_ID, "announcement_id": announcement_id, "department": record.get("deptName"),
                "published_at": published, "application_start_at": None, "application_end_at": None,
                "application_window_status": "unknown", "file_name": record.get("fileName"), "file_url": record.get("fileUrl"),
            }, route_id=query.route_id,
        )

    @staticmethod
    def _date(value: Any) -> Optional[str]:
        if not value:
            return None
        raw = str(value).strip()
        for pattern in ("%Y-%m-%d", "%Y.%m.%d", "%Y.%m.%d."):
            try:
                return datetime.strptime(raw, pattern).isoformat()
            except ValueError:
                continue
        return None

    @staticmethod
    def _matches(item: CollectedItem, query: SourceQuery) -> bool:
        params = query.params or {}
        interests = [str(value).strip() for value in params.get("raw_interests", []) if str(value).strip()]
        interest = str(params.get("raw_interest") or query.query or "").strip()
        if interest:
            interests.append(interest)
        return not interests or any(matches_interest(f"{item.title} {item.author}".casefold(), value) for value in interests)

    @staticmethod
    def _announcement_id(record: Dict[str, Any], url: str) -> str:
        direct = str(record.get("nttSeqNo") or record.get("announcementId") or record.get("id") or "").strip()
        if direct:
            return direct
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        return str((query.get("nttSeqNo") or [""])[0]).strip()

    @staticmethod
    def _fetch_json(url: str, timeout: float, headers: Dict[str, str]) -> Any:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))

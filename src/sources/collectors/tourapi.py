"""Metadata-only TourAPI festival collector (service 15101578).

The collector is intentionally dormant in the registry until an operator has
recorded API-key and reuse approval.  It stores no images, attachment files,
or description text.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery


class TourAPIFestivalCollector(BaseCollector):
    source_id = "tourapi"
    SERVICE_ID = "15101578"
    ENDPOINT = "https://apis.data.go.kr/B551011/KorService2/searchFestival2"
    MAX_PAGE_SIZE = 20

    def __init__(self, fetch_json: Optional[Callable[[str, float, Dict[str, str]], Any]] = None, timeout: float = 8.0):
        self.fetch_json = fetch_json or self._fetch_json
        self.timeout = timeout

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        key = os.environ.get("TOURAPI_SERVICE_KEY", "").strip()
        if not key:
            return CollectorResult(source=self.source_id, errors=["TOURAPI_SERVICE_KEY is required; no request was made."], items=[])
        query = queries[0] if queries else SourceQuery(source=self.source_id, query="")
        try:
            payload = self.fetch_json(self._url(key, query.params or {}, limit), self.timeout, {
                "Accept": "application/json", "User-Agent": "LUMOS/0.1",
            })
        except Exception as exc:
            return CollectorResult(source=self.source_id, errors=[f"network request failed: {exc}"], items=[])
        error = self._api_error(payload)
        if error:
            return CollectorResult(source=self.source_id, errors=[error], items=[])
        items, seen = [], set()
        for record in self._records(payload):
            item = self._normalise(record, query)
            if not item or item.source_item_id in seen:
                continue
            seen.add(item.source_item_id)
            items.append(item)
            if len(items) >= min(max(1, limit), self.MAX_PAGE_SIZE):
                break
        return CollectorResult(source=self.source_id, items=items)

    def _url(self, key: str, params: Dict[str, Any], limit: int) -> str:
        start = str(params.get("event_start_date") or self._today_kst().strftime("%Y%m%d"))
        values = {
            "serviceKey": key, "MobileOS": "ETC", "MobileApp": "LUMOS",
            "_type": "json", "eventStartDate": start,
            "numOfRows": min(max(1, int(limit or 1)), self.MAX_PAGE_SIZE), "pageNo": 1,
        }
        # Region codes are accepted only when the caller already has official
        # code values; user-entered place names are never guessed as codes.
        for key_name in ("lDongRegnCd", "lDongSignguCd"):
            if params.get(key_name):
                values[key_name] = str(params[key_name])
        return f"{self.ENDPOINT}?{urllib.parse.urlencode(values)}"

    @staticmethod
    def _records(payload: Any) -> List[Dict[str, Any]]:
        try:
            items = payload["response"]["body"]["items"]["item"]
        except (KeyError, TypeError):
            return []
        return items if isinstance(items, list) else ([items] if isinstance(items, dict) else [])

    def _normalise(self, record: Dict[str, Any], query: SourceQuery) -> Optional[CollectedItem]:
        title = str(record.get("title") or "").strip()
        content_id = str(record.get("contentid") or "").strip()
        start = self._date(record.get("eventstartdate"))
        end = self._date(record.get("eventenddate"))
        if not title or not content_id or not start:
            return None
        status = self._event_status(start, end)
        if status == "ended":
            return None
        place = " ".join(part for part in (str(record.get("addr1") or "").strip(), str(record.get("addr2") or "").strip()) if part)
        url = f"https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid={urllib.parse.quote(content_id)}"
        return CollectedItem(
            source=self.source_id, source_item_id=content_id, url=url, title=title[:300], summary="",
            author="\ud55c\uad6d\uad00\uad11\uacf5\uc0ac", published_at=start.isoformat(), route_id=query.route_id,
            metrics_json={
                "content_kind": "culture_event", "event_start_at": start.isoformat(),
                "event_end_at": end.isoformat() if end else None, "event_status": status,
                # ``addr1`` is provider-supplied location metadata, not an
                # inferred region code. It permits literal city/province
                # preference checks without broadening topic matching.
                "venue": place or None,
                # Keep the full provider address as venue, but expose its
                # literal first component as a compact regional label.
                "region": (str(record.get("addr1") or "").strip().split() or [None])[0],
                "image_collected": False,
            },
            raw_json={
                "service_id": self.SERVICE_ID, "content_id": content_id,
                "event_start_at": start.isoformat(), "event_end_at": end.isoformat() if end else None,
                "event_status": status, "venue": place or None, "image_collected": False,
            },
        )

    @staticmethod
    def _date(value: Any) -> Optional[date]:
        try:
            return datetime.strptime(str(value or ""), "%Y%m%d").date()
        except ValueError:
            return None

    def _event_status(self, start: date, end: Optional[date]) -> str:
        today = self._today_kst()
        if end and end < today:
            return "ended"
        return "upcoming" if start > today else "ongoing"

    @staticmethod
    def _today_kst() -> date:
        from src.engine.evaluation.periods import KOREA_TZ
        return datetime.now(KOREA_TZ).date()

    @staticmethod
    def _api_error(payload: Any) -> Optional[str]:
        header = ((payload or {}).get("response") or {}).get("header") if isinstance(payload, dict) else {}
        code = str((header or {}).get("resultCode") or "")
        # KorService2 uses both three- and four-digit successful result codes
        # depending on its gateway response shape. Treat ``0000`` as normal;
        # otherwise a successful HTTP response is discarded before its event
        # schedule can be normalised.
        if code and code not in {"00", "000", "0000", "NORMAL_CODE", "NORMAL_SERVICE"}:
            return f"API error {code}: {str((header or {}).get('resultMsg') or 'unspecified error')}"
        return None

    @staticmethod
    def _fetch_json(url: str, timeout: float, headers: Dict[str, str]) -> Any:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            # Never retain the request URL (which includes the service key).
            # Keep only bounded provider status fields for the next isolated
            # diagnostic run; they are enough to distinguish access denial
            # from a malformed endpoint or parameter error.
            body = exc.read(32_000).decode("utf-8", errors="replace")
            code, message = TourAPIFestivalCollector._provider_error_fields(body)
            detail = f"HTTP {exc.code}: {exc.reason}"
            if code:
                detail += f"; provider_code={code}"
            if message:
                detail += f"; provider_message={message[:200]}"
            raise RuntimeError(detail) from None

    @staticmethod
    def _provider_error_fields(body: str) -> tuple[str, str]:
        """Extract only standard error fields; never return arbitrary body text."""
        try:
            payload = json.loads(body)
        except (TypeError, ValueError):
            payload = None
        if isinstance(payload, dict):
            queue = [payload]
            while queue:
                current = queue.pop(0)
                if not isinstance(current, dict):
                    continue
                code = str(current.get("resultCode") or "")
                message = str(current.get("resultMsg") or "")
                if code or message:
                    return code, message
                queue.extend(value for value in current.values() if isinstance(value, dict))
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return "", ""
        code = root.findtext(".//resultCode") or ""
        message = root.findtext(".//resultMsg") or ""
        return str(code), str(message)

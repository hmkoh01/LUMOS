"""Metadata-only collector for service 15163956 support programmes."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

from src.context.interest_matching import matches_interest
from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery
from src.sources.response_validation import assess_list_response


class MSSSupportProgramCollector(BaseCollector):
    source_id = "mss_support_program"
    SERVICE_ID = "15163956"
    ENDPOINT = "https://apis.data.go.kr/B555280/sprtBizInfos1/getSprtBizInfos1"
    MAX_PAGE_SIZE = 20

    def __init__(self, fetch_json: Optional[Callable[[str, float, Dict[str, str]], Any]] = None, timeout: float = 8.0):
        self.fetch_json = fetch_json or self._fetch_json
        self.timeout = timeout

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        query = queries[0] if queries else SourceQuery(source=self.source_id, query="")
        params = dict(query.params or {})
        key = os.environ.get("MSS_SUPPORT_PROGRAM_API_KEY", "").strip() or os.environ.get("PUBLIC_DATA_PORTAL_SERVICE_KEY", "").strip()
        if not key:
            return CollectorResult(source=self.source_id, errors=["MSS_SUPPORT_PROGRAM_API_KEY or PUBLIC_DATA_PORTAL_SERVICE_KEY is required; no request was made."], items=[])
        year = str(params.get("sprtBizYr") or "").strip()
        if not year:
            return CollectorResult(source=self.source_id, errors=["sprtBizYr is required; no request was made."], items=[])
        try:
            payload = self.fetch_json(self._url(key, year, params, limit), self.timeout, {"Accept": "application/json", "User-Agent": "LUMOS/0.1"})
        except Exception as exc:
            return CollectorResult(source=self.source_id, errors=[f"network request failed: {exc}"], items=[])
        records = self._records(payload)
        assessment = assess_list_response(payload, records, id_field="sprtBizCd", title_field="sprtBizNm", confirmed_success_codes=frozenset())
        if assessment.state == "rejected":
            return CollectorResult(source=self.source_id, errors=[f"provider_response_rejected={assessment.reason}"], items=[])
        items, seen, rejected_status, rejected_interest, rejected_duplicate = [], set(), 0, 0, 0
        for record in records:
            item = self._normalise(record, query)
            if item is None:
                rejected_status += 1
                continue
            if item.source_item_id in seen:
                rejected_duplicate += 1
                continue
            if not self._matches(item, query):
                rejected_interest += 1
                continue
            seen.add(item.source_item_id)
            items.append(item)
            if len(items) >= min(max(1, limit), self.MAX_PAGE_SIZE):
                break
        warnings = [
            f"mss_support_records_received={len(records)}",
            f"mss_support_page_no={self._counter(payload, 'pageNo')}",
            f"mss_support_num_of_rows={self._counter(payload, 'numOfRows')}",
            f"mss_support_total_count={self._counter(payload, 'totalCount')}",
            f"mss_support_rejected_status={rejected_status}",
            f"mss_support_rejected_interest={rejected_interest}",
            f"mss_support_rejected_duplicate={rejected_duplicate}",
        ]
        warnings.append(f"mss_support_response_classification={assessment.state}")
        warnings.append(f"mss_support_response_reason={assessment.reason}")
        return CollectorResult(source=self.source_id, items=items, warnings=warnings)

    def _url(self, key: str, year: str, params: Dict[str, Any], limit: int) -> str:
        values = {"serviceKey": key, "pageNo": str(max(1, int(params.get("pageNo") or 1))), "numOfRows": str(min(max(1, limit), self.MAX_PAGE_SIZE)), "sprtBizYr": year}
        return self.ENDPOINT + "?" + urllib.parse.urlencode(values)

    @staticmethod
    def _records(payload: Any) -> List[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        value = payload.get("item")
        if isinstance(value, list):
            return [record for record in value if isinstance(record, dict)]
        return [value] if isinstance(value, dict) else []

    @staticmethod
    def _value(record: Dict[str, Any], key: str) -> Optional[str]:
        value = record.get(key)
        return str(value).strip() if value is not None and str(value).strip() else None

    @staticmethod
    def _counter(payload: Any, field: str) -> int:
        value = payload.get(field) if isinstance(payload, dict) else None
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _date(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        for pattern in ("%Y%m%d", "%Y-%m-%d", "%Y.%m.%d"):
            try:
                return datetime.strptime(value, pattern).date().isoformat()
            except ValueError:
                pass
        return None

    @staticmethod
    def _is_new_application(title: str, stage: Optional[str]) -> bool:
        text = f"{title} {stage or ''}".casefold()
        return not any(term in text for term in ("선정결과", "선정 결과", "최종선정", "합격자", "결과발표", "협약체결", "selection result", "award result"))

    def _normalise(self, record: Dict[str, Any], query: SourceQuery) -> Optional[CollectedItem]:
        program_id, title = self._value(record, "sprtBizCd"), self._value(record, "sprtBizNm")
        if not program_id or not title:
            return None
        stage = self._value(record, "progrsSttusNm")
        if not self._is_new_application(title, stage):
            return None
        start, end = self._date(self._value(record, "rcritBgngYmd")), self._date(self._value(record, "rcritEndYmd"))
        if end and end < date.today().isoformat():
            return None
        status = "unknown" if not start or not end else ("upcoming" if start > date.today().isoformat() else "ongoing")
        categories = [self._value(record, name) for name in ("sprtBizCg1Nm", "sprtBizCg2Nm", "sprtBizCg3Nm", "sprtBizCgDtlNm")]
        return CollectedItem(
            source=self.source_id, source_item_id=program_id, title=title[:300], url=self._value(record, "sprtBizUrl") or "", summary="",
            author=self._value(record, "operInstNm") or "", published_at=start, route_id=query.route_id,
            metrics_json={"content_kind": "startup_program", "program_id": program_id, "support_target": self._value(record, "sprtBizTrgtNm") or "", "region": self._value(record, "sprtBizCtpvNm") or "", "stage": stage or "", "application_start_at": start, "application_end_at": end, "application_window_status": status, "support_type": self._value(record, "sprtBizTyNm") or "", "categories": [value for value in categories if value], "purpose": self._value(record, "sprtBizPurpose") or ""},
            raw_json={"service_id": self.SERVICE_ID, "program_id": program_id, "program_year": self._value(record, "sprtBizYr"), "preserve_missing_published_at": True},
        )

    @staticmethod
    def _matches(item: CollectedItem, query: SourceQuery) -> bool:
        params = query.params or {}
        if params.get("collection_scope"):
            # Shared source collection preserves the complete bounded pool.
            # Personal profile matching is evaluated after dedupe, rather than
            # discarding another user's relevant programme at collection time.
            return True
        interest = str(params.get("raw_interest") or query.query or "").strip()
        if not interest:
            return True
        data = item.metrics_json
        text = " ".join([item.title, item.author, str(data.get("support_target") or ""), str(data.get("region") or ""), str(data.get("support_type") or ""), str(data.get("purpose") or ""), *map(str, data.get("categories") or [])]).casefold()
        return matches_interest(text, interest)

    @staticmethod
    def _fetch_json(url: str, timeout: float, headers: Dict[str, str]) -> Any:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
            return json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))

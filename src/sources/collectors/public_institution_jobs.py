"""Public-institution recruitment collector for service 15125273 list only."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.context.interest_matching import matches_interest
from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery
from src.sources.response_validation import assess_list_response
from src.sources.domestic_collection_strategy import has_developer_role_evidence


class PublicInstitutionJobsCollector(BaseCollector):
    source_id = "public_institution_jobs"
    SERVICE_ID = "15125273"
    ENDPOINT = "https://apis.data.go.kr/1051000/recruitment/list"
    MAX_PAGE_SIZE = 20

    def __init__(self, fetch_json: Optional[Callable[[str, float, Dict[str, str]], Any]] = None, timeout: float = 8.0):
        self.fetch_json = fetch_json or self._fetch_json
        self.timeout = timeout

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        query = queries[0] if queries else SourceQuery(source=self.source_id, query="")
        params = dict(query.params or {})
        key = os.environ.get("PUBLIC_INSTITUTION_JOBS_API_KEY", "").strip() or os.environ.get("PUBLIC_DATA_PORTAL_SERVICE_KEY", "").strip()
        if not key:
            return CollectorResult(source=self.source_id, errors=["PUBLIC_INSTITUTION_JOBS_API_KEY or PUBLIC_DATA_PORTAL_SERVICE_KEY is required; no request was made."], items=[])
        try:
            payload = self.fetch_json(self._url(key, params, limit), self.timeout, {"Accept": "application/json", "User-Agent": "LUMOS/0.1"})
        except Exception as exc:
            return CollectorResult(source=self.source_id, errors=[f"network request failed: {exc}"], items=[])
        records = self._records(payload)
        assessment = assess_list_response(payload, records, id_field="recrutPblntSn", title_field="recrutPbancTtl", confirmed_success_codes=frozenset({"0"}))
        if assessment.state == "rejected":
            return CollectorResult(source=self.source_id, errors=[f"provider_response_rejected={assessment.reason}"], items=[])
        items, seen, rejected_interest, rejected_duplicate = [], set(), 0, 0
        for record in records:
            item = self._normalise(record, query)
            if not item:
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
        return CollectorResult(source=self.source_id, items=items, warnings=[
            f"public_jobs_records_received={len(records)}",
            f"public_jobs_page_no={self._counter(payload, 'pageNo')}",
            f"public_jobs_num_of_rows={self._counter(payload, 'numOfRows')}",
            f"public_jobs_total_count={self._counter(payload, 'totalCount')}",
            f"public_jobs_rejected_interest={rejected_interest}",
            f"public_jobs_rejected_duplicate={rejected_duplicate}",
            f"public_jobs_response_classification={assessment.state}",
            f"public_jobs_response_reason={assessment.reason}",
        ])

    def _url(self, key: str, params: Dict[str, Any], limit: int) -> str:
        values = {"serviceKey": key, "pageNo": str(max(1, int(params.get("pageNo") or 1))), "numOfRows": str(min(max(1, limit), self.MAX_PAGE_SIZE)), "ongoingYn": str(params.get("ongoingYn") or "Y"), "resultType": str(params.get("resultType") or "json")}
        for name in ("recrutSe", "hireTypeLst", "workRgnLst", "ncsCdLst", "recrutPbancTtl", "pbancBgngYmd", "pbancEndYmd"):
            if params.get(name):
                values[name] = str(params[name])
        return self.ENDPOINT + "?" + urllib.parse.urlencode(values)

    @staticmethod
    def _records(payload: Any) -> List[Dict[str, Any]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("result"), list):
            return []
        records: List[Dict[str, Any]] = []
        for envelope in payload["result"]:
            if isinstance(envelope, dict) and isinstance(envelope.get("item"), dict):
                records.append(envelope["item"])
            elif isinstance(envelope, dict):
                # The service sometimes documents an item object directly in
                # the result array; retain only records carrying the official ID.
                records.append(envelope)
        return records

    @staticmethod
    def _value(record: Dict[str, Any], key: str) -> Optional[str]:
        value = record.get(key)
        if isinstance(value, list):
            value = ", ".join(str(part).strip() for part in value if str(part).strip())
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

    def _normalise(self, record: Dict[str, Any], query: SourceQuery) -> Optional[CollectedItem]:
        identifier, title = self._value(record, "recrutPblntSn"), self._value(record, "recrutPbancTtl")
        if not identifier or not title:
            return None
        start, end = self._date(self._value(record, "pbancBgngYmd")), self._date(self._value(record, "pbancEndYmd"))
        ongoing = self._value(record, "ongoingYn")
        # The public list specification documents pbancEndYmd as a *request*
        # range bound ("search end date based on recruitment notice start
        # date"), not as an application deadline.  A provider record can
        # contain a field with that name, but its per-record meaning is not
        # established by the list model.  Preserve it only as explicitly
        # unverified provider metadata; never promote it to a card date,
        # application deadline, or an "open" status.
        return CollectedItem(
            source=self.source_id, source_item_id=identifier, title=title[:300], url=self._value(record, "srcUrl") or "", summary="",
            author=self._value(record, "instNm") or "", published_at=start, route_id=query.route_id,
            metrics_json={"content_kind": "public_institution_job", "announcement_start_at": start, "provider_pbanc_end_ymd_unverified": end, "provider_ongoing": ongoing, "application_window_status": "unknown", "job_type": self._value(record, "hireTypeNmLst") or "", "region": self._value(record, "workRgnNmLst") or "", "job_classification": self._value(record, "ncsCdNmLst") or "", "recruitment_type": self._value(record, "recrutSeNm") or "", "recruitment_headcount": self._value(record, "recrutNope") or ""},
            raw_json={"service_id": self.SERVICE_ID, "preserve_missing_published_at": True},
        )

    @staticmethod
    def _matches(item: CollectedItem, query: SourceQuery) -> bool:
        params = query.params or {}
        data = item.metrics_json
        role_text = " ".join([
            item.title, str(data.get("job_type") or ""), str(data.get("job_classification") or ""),
            str(data.get("recruitment_type") or ""),
        ]).casefold()
        direct_terms = [str(term).casefold() for term in params.get("direct_evidence_terms") or [] if str(term).strip()]
        # A developer profile must be supported by job-role metadata, not by
        # the word "intern" alone.  Other opportunity profiles (intern or
        # junior recruitment) instead require their own direct provider
        # evidence; they must not be sent through the developer-role gate.
        if params.get("requires_developer_role_evidence") and not has_developer_role_evidence(
            item.title, data.get("job_type"), data.get("job_classification"), data.get("recruitment_type"),
        ):
            return False
        if direct_terms and not params.get("requires_developer_role_evidence") and not any(
            term in role_text for term in direct_terms
        ):
            return False
        if params.get("collection_scope"):
            return True
        interest = str(params.get("raw_interest") or query.query or "").strip()
        if not interest:
            return True
        return matches_interest(" ".join([item.title, item.author, str(data.get("job_type") or ""), str(data.get("region") or ""), str(data.get("job_classification") or ""), str(data.get("recruitment_type") or "")]).casefold(), interest)

    @staticmethod
    def _fetch_json(url: str, timeout: float, headers: Dict[str, str]) -> Any:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
            return json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))

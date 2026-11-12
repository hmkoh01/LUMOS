"""Metadata-only OpenDART disclosure collector with verified company lookup."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery
from src.sources.collectors.domestic_common import parse_date
from src.sources.opendart_corporations import CorporationCodeCache, SHARED_CORPORATION_CODE_CACHE


class OpenDARTCollector(BaseCollector):
    source_id = "opendart"
    ENDPOINT = "https://opendart.fss.or.kr/api/list.json"

    def __init__(
        self,
        fetch_json: Optional[Callable[[str, float, Dict[str, str]], Any]] = None,
        timeout: float = 8.0,
        corporation_cache: CorporationCodeCache | None = None,
    ) -> None:
        self.fetch_json = fetch_json or self._fetch
        self.timeout = timeout
        self.corporation_cache = corporation_cache or SHARED_CORPORATION_CODE_CACHE

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        key = os.environ.get("OPENDART_API_KEY", "").strip()
        if not key:
            return CollectorResult(source=self.source_id, errors=["OPENDART_API_KEY is required; no request was made."], items=[])
        query = queries[0] if queries else SourceQuery(source=self.source_id, query="")
        params = dict(query.params or {})
        if not params.get("bgn_de") or not params.get("end_de"):
            return CollectorResult(source=self.source_id, errors=["bgn_de and end_de are required; no request was made."], items=[])

        company = str(params.get("company_name") or params.get("raw_interest") or query.query or "").strip()
        if not company:
            return CollectorResult(source=self.source_id, warnings=["opendart_explicit_company_required"], items=[], attempted=False)
        resolution = self.corporation_cache.resolve(company)
        verified_stock_code = str(params.get("verified_stock_code") or "").strip()
        # An alias may be used only after an operator supplied a stock code
        # backed by an official issuer/market record. The cache must resolve
        # that exact code to one corporation; there is no fuzzy name fallback.
        if resolution.state != "resolved" and verified_stock_code:
            by_stock = getattr(self.corporation_cache, "resolve_stock_code", None)
            if callable(by_stock):
                resolution = by_stock(verified_stock_code)
        if resolution.state != "resolved" or resolution.record is None:
            return CollectorResult(
                source=self.source_id,
                warnings=[f"opendart_corp_code_{resolution.state}"],
                items=[],
                attempted=False,
            )
        # The only accepted corp_code is an exact, official mapping for the
        # requested company. A caller-supplied value cannot override it.
        params["corp_code"] = resolution.record.corp_code
        params["company_name"] = resolution.record.corp_name
        try:
            payload = self.fetch_json(self._url(key, params), self.timeout, {
                "Accept": "application/json", "User-Agent": "LUMOS/0.1",
            })
        except Exception as exc:
            return CollectorResult(source=self.source_id, errors=[f"network request failed: {exc}"], items=[])
        status = str(payload.get("status") or "") if isinstance(payload, dict) else ""
        # OpenDART's official code table defines 013 as "no data found". It
        # is a successful empty search, not a provider failure and never a
        # reason to widen dates or retry a company query.
        if status == "013":
            return CollectorResult(source=self.source_id, warnings=["opendart_no_data"], items=[])
        if status and status != "000":
            return CollectorResult(source=self.source_id, errors=[f"API error {status}: {str(payload.get('message') or 'unspecified error')}"], items=[])

        items: List[CollectedItem] = []
        seen: set[str] = set()
        for record in (payload.get("list") or []) if isinstance(payload, dict) else []:
            if str(record.get("corp_code") or "").strip() != resolution.record.corp_code:
                continue
            item = self._normalise(record, query)
            if not item or item.source_item_id in seen or not self._matches(item, params):
                continue
            seen.add(item.source_item_id)
            items.append(item)
            if len(items) >= min(max(1, int(limit or 1)), 10):
                break
        return CollectorResult(source=self.source_id, items=items)

    def _url(self, key: str, params: Dict[str, Any]) -> str:
        values = {
            "crtfc_key": key,
            "corp_code": str(params["corp_code"]),
            "bgn_de": str(params["bgn_de"]),
            "end_de": str(params["end_de"]),
            "page_no": str(max(1, int(params.get("page_no") or 1))),
            "page_count": str(min(max(1, int(params.get("page_count") or 10)), 10)),
        }
        for name in ("corp_cls", "last_reprt_at", "pblntf_ty", "pblntf_detail_ty", "sort", "sort_mth"):
            if params.get(name):
                values[name] = str(params[name])
        return self.ENDPOINT + "?" + urllib.parse.urlencode(values)

    def _normalise(self, record: Dict[str, Any], query: SourceQuery) -> Optional[CollectedItem]:
        identifier = str(record.get("rcept_no") or "").strip()
        title = str(record.get("report_nm") or "").strip()
        if not identifier or not title:
            return None
        published = parse_date(record.get("rcept_dt"))
        url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={urllib.parse.quote(identifier)}"
        return CollectedItem(
            source=self.source_id,
            source_item_id=identifier,
            title=title[:300],
            url=url,
            summary="",
            author=str(record.get("corp_name") or "")[:120],
            published_at=published,
            route_id=query.route_id,
            metrics_json={
                "content_kind": "corporate_disclosure",
                "receipt_at": published,
                "corporation_code": str(record.get("corp_code") or ""),
                "corporation_class": record.get("corp_cls"),
                "filer": record.get("flr_nm"),
            },
            raw_json={"rcept_no": identifier, "preserve_missing_published_at": True},
        )

    @staticmethod
    def _matches(item: CollectedItem, params: Dict[str, Any]) -> bool:
        company = str(params.get("company_name") or "").strip()
        expected_code = str(params.get("corp_code") or "").strip()
        if not company or not expected_code:
            return False
        normalise = lambda value: " ".join(str(value or "").casefold().split())
        return (
            normalise(company) == normalise(item.author)
            and expected_code == str(item.metrics_json.get("corporation_code") or "").strip()
        )

    @staticmethod
    def _fetch(url: str, timeout: float, headers: Dict[str, str]) -> Any:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
            return json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))

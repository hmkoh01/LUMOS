"""Schema-bound collectors for sources whose issued field model is unavailable.

They are real Collector implementations: fixtures can exercise their complete
normalisation and safety policy.  A live call is impossible until an operator
records the issued endpoint, envelope and field map; this prevents a catalogue
display label from silently becoming a fabricated API schema.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from src.context.interest_matching import matches_interest
from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery
from src.sources.collectors.domestic_common import dated_status, parse_date


class SchemaPendingMetadataCollector(BaseCollector):
    source_id = ""
    service_id = ""
    env_key = ""
    env_url = ""
    content_kind = ""
    required_fields = frozenset({"id", "title", "source_url"})

    def __init__(self, fetch_json: Optional[Callable[[str, float, Dict[str, str]], Any]] = None, timeout: float = 8.0):
        self.fetch_json = fetch_json or self._fetch_json
        self.timeout = timeout

    def collect(self, queries: List[SourceQuery], limit: int) -> CollectorResult:
        query = queries[0] if queries else SourceQuery(source=self.source_id, query="")
        config = dict(query.params or {})
        # The explicit guard is deliberately before any URL construction.
        if config.get("schema_confirmed") is not True:
            return CollectorResult(source=self.source_id, warnings=["schema_pending: issued operation/model required; no request was made."], items=[], attempted=False)
        api_key = os.environ.get(self.env_key, "").strip()
        endpoint = str(config.get("api_url") or os.environ.get(self.env_url, "")).strip()
        field_map = config.get("field_map") if isinstance(config.get("field_map"), dict) else {}
        records_path = config.get("records_path")
        missing = sorted(self.required_fields.difference(field_map))
        if not api_key:
            return CollectorResult(source=self.source_id, errors=[f"{self.env_key} is required; no request was made."], items=[])
        if not endpoint or not isinstance(records_path, list) or missing:
            return CollectorResult(source=self.source_id, errors=["issued endpoint, records_path and complete field_map are required; no request was made."], items=[])
        params = dict(config.get("request_params") or {})
        params[str(config.get("auth_parameter") or "serviceKey")] = api_key
        params.setdefault("numOfRows", min(max(1, limit), 20))
        url = f"{endpoint}{'&' if '?' in endpoint else '?'}{urllib.parse.urlencode(params)}"
        try:
            payload = self.fetch_json(url, self.timeout, {"Accept": "application/json", "User-Agent": "LUMOS/0.1"})
        except Exception as exc:
            return CollectorResult(source=self.source_id, errors=[f"network request failed: {exc}"], items=[])
        records = self._records(payload, records_path)
        items, seen = [], set()
        for record in records:
            item = self._normalise(record, field_map, query)
            if not item or item.source_item_id in seen or not self._matches(item, query):
                continue
            seen.add(item.source_item_id)
            items.append(item)
            if len(items) >= limit:
                break
        return CollectorResult(source=self.source_id, items=items)

    @staticmethod
    def _records(payload: Any, path: List[str]) -> List[Dict[str, Any]]:
        current = payload
        for key in path:
            if not isinstance(current, dict):
                return []
            current = current.get(key)
        return [value for value in current if isinstance(value, dict)] if isinstance(current, list) else ([current] if isinstance(current, dict) else [])

    def _normalise(self, record: Dict[str, Any], field_map: Dict[str, str], query: SourceQuery) -> Optional[CollectedItem]:
        def value(name: str) -> Optional[str]:
            raw = record.get(field_map.get(name, ""))
            return str(raw).strip() if raw is not None and str(raw).strip() else None
        identifier, title = value("id"), value("title")
        if not identifier or not title:
            return None
        start, end = parse_date(value("start_at")), parse_date(value("end_at"))
        status = dated_status(start, end)
        if status == "ended":
            return None
        return CollectedItem(
            source=self.source_id, source_item_id=identifier, title=title[:300], url=value("source_url") or "", summary="",
            author=value("publisher") or "", published_at=parse_date(value("published_at")), route_id=query.route_id,
            metrics_json={"content_kind": self.content_kind, "start_at": start, "end_at": end, "status": status,
                          "region": value("region"), "target": value("target"), "job_type": value("job_type")},
            raw_json={"service_id": self.service_id, "preserve_missing_published_at": True, "status": status},
        )

    @staticmethod
    def _matches(item: CollectedItem, query: SourceQuery) -> bool:
        interest = str((query.params or {}).get("raw_interest") or query.query or "").strip()
        return not interest or matches_interest(f"{item.title} {item.author}".casefold(), interest)

    @staticmethod
    def _fetch_json(url: str, timeout: float, headers: Dict[str, str]) -> Any:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))


class PublicInstitutionJobsCollector(SchemaPendingMetadataCollector):
    source_id, service_id = "public_institution_jobs", "15125273"
    env_key, env_url, content_kind = "PUBLIC_INSTITUTION_JOBS_API_KEY", "PUBLIC_INSTITUTION_JOBS_API_URL", "public_institution_job"
    required_fields = SchemaPendingMetadataCollector.required_fields | {"start_at", "end_at", "job_type", "region"}


class PublicServiceJobsCollector(SchemaPendingMetadataCollector):
    source_id, service_id = "public_service_jobs", "15156780"
    env_key, env_url, content_kind = "PUBLIC_SERVICE_JOBS_API_KEY", "PUBLIC_SERVICE_JOBS_API_URL", "public_service_job"
    required_fields = SchemaPendingMetadataCollector.required_fields | {"start_at", "end_at", "job_type", "region"}


class YouthCenterPolicyCollector(SchemaPendingMetadataCollector):
    source_id, service_id = "youthcenter_policy", "youthcenter"
    env_key, env_url, content_kind = "YOUTHCENTER_API_KEY", "YOUTHCENTER_API_URL", "youth_policy"
    required_fields = SchemaPendingMetadataCollector.required_fields | {"start_at", "end_at", "target", "region"}


class SeoulCultureEventsCollector(SchemaPendingMetadataCollector):
    source_id, service_id = "seoul_culture_events", "OA-23041"
    env_key, env_url, content_kind = "SEOUL_OPEN_DATA_API_KEY", "SEOUL_CULTURE_EVENTS_API_URL", "culture_event"
    required_fields = SchemaPendingMetadataCollector.required_fields | {"start_at", "end_at", "region"}

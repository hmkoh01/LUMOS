"""Shared, verified OpenDART corporation-code lookup.

The official ``corpCode.xml`` endpoint returns a ZIP containing corporation
metadata.  This module deliberately does not fetch it during an individual
user's disclosure query: an operator or shared collection job must refresh the
cache first.  That avoids one extra API request per user and prevents guessed
corporation codes from reaching ``list.json``.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from threading import RLock
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Literal
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


ResolutionState = Literal["resolved", "not_found", "ambiguous", "cache_unavailable"]
CORPORATION_CODE_ENDPOINT = "https://opendart.fss.or.kr/api/corpCode.xml"


@dataclass(frozen=True)
class CorporationRecord:
    corp_code: str
    corp_name: str
    stock_code: str = ""
    modify_date: str = ""


@dataclass(frozen=True)
class CorporationResolution:
    state: ResolutionState
    record: CorporationRecord | None = None


class CorporationCodeCache:
    """Thread-safe, source-wide exact-name cache built from official data."""

    def __init__(self) -> None:
        self._by_name: Dict[str, tuple[CorporationRecord, ...]] = {}
        self._lock = RLock()

    @property
    def loaded(self) -> bool:
        with self._lock:
            return bool(self._by_name)

    def replace_from_zip(self, payload: bytes) -> int:
        """Atomically load official records; malformed archives change nothing."""
        records = list(parse_corporation_zip(payload))
        grouped: Dict[str, list[CorporationRecord]] = {}
        for record in records:
            grouped.setdefault(normalize_corporation_name(record.corp_name), []).append(record)
        if not grouped:
            raise ValueError("official corporation-code archive contains no valid records")
        with self._lock:
            self._by_name = {name: tuple(values) for name, values in grouped.items()}
        return len(records)

    def resolve(self, corporation_name: str) -> CorporationResolution:
        key = normalize_corporation_name(corporation_name)
        with self._lock:
            if not self._by_name:
                return CorporationResolution("cache_unavailable")
            matches = self._by_name.get(key, ())
        if not matches:
            return CorporationResolution("not_found")
        if len(matches) != 1:
            return CorporationResolution("ambiguous")
        return CorporationResolution("resolved", matches[0])


def parse_corporation_zip(payload: bytes) -> Iterable[CorporationRecord]:
    """Yield only valid official XML rows, without retaining the archive."""
    try:
        with ZipFile(BytesIO(payload)) as archive:
            xml_names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
            if len(xml_names) != 1:
                raise ValueError("official corporation-code archive must contain one XML document")
            root = ET.fromstring(archive.read(xml_names[0]))
    except (BadZipFile, ET.ParseError, OSError) as exc:
        raise ValueError("invalid official corporation-code archive") from exc
    for row in root.findall(".//list"):
        corp_code = str(row.findtext("corp_code") or "").strip()
        corp_name = str(row.findtext("corp_name") or "").strip()
        if not re.fullmatch(r"\d{8}", corp_code) or not corp_name:
            continue
        yield CorporationRecord(
            corp_code=corp_code,
            corp_name=corp_name,
            stock_code=str(row.findtext("stock_code") or "").strip(),
            modify_date=str(row.findtext("modify_date") or "").strip(),
        )


def normalize_corporation_name(value: str) -> str:
    """Exact-name lookup normalisation only; no aliases or fuzzy inference."""
    return " ".join(str(value or "").casefold().split())


SHARED_CORPORATION_CODE_CACHE = CorporationCodeCache()


class QueueCorporationCodeCache:
    """Adapter for the existing multi-Worker Engine queue SQLite database."""

    def __init__(self, queue: Any, *, max_age_seconds: int = 7 * 24 * 60 * 60) -> None:
        self.queue = queue
        self.max_age_seconds = max(0, int(max_age_seconds))

    def replace_from_zip(self, payload: bytes) -> int:
        records = list(parse_corporation_zip(payload))
        return self.queue.replace_opendart_corporation_directory([
            {
                "normalized_name": normalize_corporation_name(record.corp_name),
                "corp_code": record.corp_code,
                "corp_name": record.corp_name,
                "stock_code": record.stock_code,
                "modify_date": record.modify_date,
            }
            for record in records
        ])

    def resolve(self, corporation_name: str) -> CorporationResolution:
        resolved = self.queue.resolve_opendart_corporation(
            normalize_corporation_name(corporation_name), max_age_seconds=self.max_age_seconds,
        )
        if resolved.get("state") != "resolved":
            # ``cache_stale`` remains deliberately distinct internally but is
            # conservatively unavailable to the Collector.
            state = "cache_unavailable" if resolved.get("state") == "cache_stale" else resolved.get("state", "cache_unavailable")
            return CorporationResolution(state)  # type: ignore[arg-type]
        return CorporationResolution("resolved", CorporationRecord(
            corp_code=str(resolved["corp_code"]), corp_name=str(resolved["corp_name"]),
            stock_code=str(resolved.get("stock_code") or ""), modify_date=str(resolved.get("modify_date") or ""),
        ))

    def resolve_stock_code(self, stock_code: str) -> CorporationResolution:
        """Use an operator-verified exact stock code; never fuzzy-match names."""
        resolved = self.queue.resolve_opendart_corporation_by_stock_code(
            str(stock_code), max_age_seconds=self.max_age_seconds,
        )
        if resolved.get("state") != "resolved":
            state = "cache_unavailable" if resolved.get("state") == "cache_stale" else resolved.get("state", "cache_unavailable")
            return CorporationResolution(state)  # type: ignore[arg-type]
        return CorporationResolution("resolved", CorporationRecord(
            corp_code=str(resolved["corp_code"]), corp_name=str(resolved["corp_name"]),
            stock_code=str(resolved.get("stock_code") or ""), modify_date=str(resolved.get("modify_date") or ""),
        ))


def refresh_shared_corporation_cache(
    api_key: str,
    *,
    fetch_bytes: Callable[[str, float, Dict[str, str]], bytes] | None = None,
    timeout: float = 20.0,
) -> int:
    """Explicitly refresh the shared directory once; never call per user.

    Callers must schedule and budget this separately from ``list.json``. The
    Collector never invokes this function, so an unknown company cannot cause
    an unbounded or user-triggered corporation-directory request.
    """
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("OPENDART_API_KEY is required for corporation-directory refresh")
    url = CORPORATION_CODE_ENDPOINT + "?" + urllib.parse.urlencode({"crtfc_key": key})
    fetch = fetch_bytes or _fetch_zip
    payload = fetch(url, timeout, {"Accept": "application/zip", "User-Agent": "LUMOS/0.1"})
    return SHARED_CORPORATION_CODE_CACHE.replace_from_zip(payload)


def refresh_queue_corporation_cache(
    queue: Any,
    api_key: str,
    *,
    max_requests_per_day: int = 1,
    fetch_bytes: Callable[[str, float, Dict[str, str]], bytes] | None = None,
    timeout: float = 20.0,
) -> int:
    """Refresh the durable directory under the Queue's shared request cap.

    This is intentionally an explicit operator/Worker action, not a side
    effect of a user's company search.  The queue's atomic reservation means
    concurrent Workers cannot download the ZIP twice on the same UTC day when
    the cap is one. Failed attempts consume the slot and are not retried here.
    """
    request_day = datetime.now(timezone.utc).date().isoformat()
    if not queue.reserve_source_request("opendart_corp_directory", request_day, max_requests_per_day):
        raise RuntimeError("opendart_corp_directory_request_budget_exhausted")
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("OPENDART_API_KEY is required for corporation-directory refresh")
    url = CORPORATION_CODE_ENDPOINT + "?" + urllib.parse.urlencode({"crtfc_key": key})
    fetch = fetch_bytes or _fetch_zip
    payload = fetch(url, timeout, {"Accept": "application/zip", "User-Agent": "LUMOS/0.1"})
    return QueueCorporationCodeCache(queue).replace_from_zip(payload)


def _fetch_zip(url: str, timeout: float, headers: Dict[str, str]) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
        return response.read(20_000_000)

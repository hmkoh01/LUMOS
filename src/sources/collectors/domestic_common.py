"""Small, conservative helpers shared by domestic metadata collectors."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional


def parse_date(value: Any) -> Optional[str]:
    """Return an ISO date only for an explicitly valid provider date."""
    raw = str(value or "").strip()
    if not raw:
        return None
    for pattern in ("%Y%m%d", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def dated_status(start_at: Optional[str], end_at: Optional[str], *, today: Optional[date] = None) -> str:
    """Classify only a supplied date window; absence is never inferred open."""
    if not start_at or not end_at:
        return "unknown"
    now = today or date.today()
    start, end = date.fromisoformat(start_at), date.fromisoformat(end_at)
    if end < now:
        return "ended"
    if start > now:
        return "upcoming"
    return "ongoing"


def first_text(record: dict, *names: str) -> Optional[str]:
    for name in names:
        value = record.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None

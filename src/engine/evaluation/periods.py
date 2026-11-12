"""Date-range utilities for daily, weekly, and monthly periods.

All boundaries use KST (UTC+9) and the user's confirmed date boundaries.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple

from src.engine.models import Period

KOREA_TZ = timezone(timedelta(hours=9))


def today_kst() -> date:
    return datetime.now(KOREA_TZ).date()


def period_range(period: str, reference: Optional[date] = None) -> Tuple[date, date]:
    """Return inclusive (start, end) date pair for the given period.

    Daily: the current KST date (the collector supplies timestamped items).
    Weekly: the trailing seven KST calendar dates including ``reference``.
    Monthly: the trailing thirty KST calendar dates including ``reference``.
    """
    ref = reference or today_kst()

    if period == Period.DAILY:
        return ref, ref

    if period == Period.WEEKLY:
        return ref - timedelta(days=6), ref

    if period == Period.MONTHLY:
        return ref - timedelta(days=29), ref

    raise ValueError(f"Unknown period: {period}")


def api_period_to_engine(api_period: str) -> str:
    """Map the legacy API period names to engine Period values."""
    return {
        "today": Period.DAILY,
        "week": Period.WEEKLY,
        "month": Period.MONTHLY,
    }.get(api_period, Period.DAILY)

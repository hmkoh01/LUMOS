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

    Daily: today only.
    Weekly: Monday..Sunday containing ``reference``.
    Monthly: 1st..last day of month containing ``reference``.
    """
    ref = reference or today_kst()

    if period == Period.DAILY:
        return ref, ref

    if period == Period.WEEKLY:
        start = ref - timedelta(days=ref.weekday())  # Monday
        end = start + timedelta(days=6)  # Sunday
        return start, end

    if period == Period.MONTHLY:
        start = ref.replace(day=1)
        # Last day of month
        if ref.month == 12:
            end = ref.replace(year=ref.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = ref.replace(month=ref.month + 1, day=1) - timedelta(days=1)
        return start, end

    raise ValueError(f"Unknown period: {period}")


def api_period_to_engine(api_period: str) -> str:
    """Map the legacy API period names to engine Period values."""
    return {
        "today": Period.DAILY,
        "week": Period.WEEKLY,
        "month": Period.MONTHLY,
    }.get(api_period, Period.DAILY)

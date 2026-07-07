from datetime import timedelta

from fastapi import APIRouter, Depends

from src.cloud.auth import normalize_plan, require_session
from src.product.entitlement_cache import DEFAULT_CACHE_TTL_HOURS, DEFAULT_OFFLINE_GRACE_DAYS, format_time, utc_now
from src.product.entitlements import MockEntitlementService

router = APIRouter(prefix="/entitlements", tags=["cloud-entitlements"])


def coerce_value(value: str):
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        return value


@router.get("/me")
def my_entitlements(session: dict = Depends(require_session)):
    plan = normalize_plan(session["plan"])
    entitlements = MockEntitlementService(plan).get_entitlements(session["user_id"], session.get("device_id") or "")
    now = utc_now()
    return {
        "plan": plan,
        "entitlements": {key: coerce_value(item.value) for key, item in entitlements.items()},
        "fetched_at": format_time(now),
        "expires_at": format_time(now + timedelta(hours=DEFAULT_CACHE_TTL_HOURS)),
        "grace_until": format_time(now + timedelta(days=DEFAULT_OFFLINE_GRACE_DAYS)),
        "source": "cloud_dev",
        "is_dev": True,
        "dev_only": True,
    }

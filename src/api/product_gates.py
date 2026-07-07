from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.product_cloud import current_feature_gate_context
from src.product.feature_gates import FeatureGateContext, StaticFeatureGateService

router = APIRouter(prefix="/product/gates", tags=["product-gates"])


class GateEvaluateRequest(BaseModel):
    feature_key: str
    current_value: Optional[Any] = None


def _context() -> FeatureGateContext:
    raw = current_feature_gate_context()
    cache_status = raw.get("cache_status") or {}
    return FeatureGateContext(
        plan=raw.get("plan") or "local_mvp",
        entitlements=raw.get("entitlements") or {},
        cache_status=cache_status.get("status", "empty"),
        cache_decision=cache_status.get("decision", "fallback_local"),
        is_dev=bool(raw.get("is_dev", True)),
        is_enforced=False,
    )


@router.get("/status")
def gate_status():
    context = _context()
    service = StaticFeatureGateService()
    return {
        "mode": current_feature_gate_context().get("mode", "local"),
        "plan": context.plan,
        "is_enforced": False,
        "cache_status": context.cache_status,
        "message": "현재는 안내만 표시하고 모든 핵심 기능을 계속 사용할 수 있어요.",
        "gates": [decision.to_dict() for decision in service.summary(context)],
    }


@router.post("/evaluate")
def evaluate_gate(request: GateEvaluateRequest):
    decision = StaticFeatureGateService().evaluate(_context(), request.feature_key, request.current_value)
    return decision.to_dict()


from fastapi import APIRouter, Depends

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.models import (
    FeedbackLearningRuleReset,
    FeedbackLearningSettingsUpdate,
    InformationTypePreferencesUpdate,
    OnboardingPreviewRequest,
    OnboardingRequest,
)
from src.context.onboarding import OnboardingService
from src.engine.collection.source_support import collection_support
from src.engine.config import EngineConfig
from src.sources.information_types import options_for_categories
from src.sources.interest_clarification import clarification_for_interest
from src.sources.router import SourceRouter
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["profile"])


def _learning_display_name(rule):
    feature, value, adjustment = rule.get("feature"), rule.get("value"), float(rule.get("adjustment") or 0)
    if feature == "specificity" and value == "specific" and adjustment > 0:
        return "더 구체적인 정보 선호"
    if feature == "difficulty" and value == "advanced" and adjustment < 0:
        return "기술적인 설명보다 쉬운 설명 선호"
    if feature == "difficulty" and value == "beginner" and adjustment > 0:
        return "쉽게 설명한 정보 선호"
    if feature == "novelty" and value == "new" and adjustment > 0:
        return "최근 발표된 정보 선호"
    if feature == "topic":
        return f"{value} 관련 정보 {'선호' if adjustment > 0 else '줄이기'}"
    if feature == "information_type":
        return f"선택한 정보 유형 {'선호' if adjustment > 0 else '우선순위 낮추기'}"
    return "피드백에서 확인된 읽기 선호"


@router.get("/profile/feedback-learning")
def get_feedback_learning(
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    """Read a compact user-facing summary; no ranking or source state changes."""
    from src.engine.personalization.feedback_experiment import derive_feedback_rules
    settings = store.get_feedback_learning_settings(user_id=current_user.id)
    rules = derive_feedback_rules(
        store.get_feedback_preference_details(user_id=current_user.id),
        reset_at=settings.get("reset_at"), rule_resets=store.get_feedback_learning_rule_resets(user_id=current_user.id),
    ) if settings.get("enabled", True) else []
    return {
        "success": True,
        "enabled": bool(settings.get("enabled", True)),
        "preferences": [
            {"feature": rule.feature, "value": rule.value, "label": _learning_display_name(rule.__dict__)}
            for rule in rules
        ],
        # The future switch is intentionally separate from this reader control.
        "production_enabled": False,
    }


@router.put("/profile/feedback-learning")
def update_feedback_learning(
    request: FeedbackLearningSettingsUpdate,
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user),
):
    return {"success": True, "settings": store.set_feedback_learning_enabled(request.enabled, user_id=current_user.id),
            "production_enabled": False}


@router.delete("/profile/feedback-learning")
def reset_all_feedback_learning(
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user),
):
    return {"success": True, "data": store.reset_feedback_learning(user_id=current_user.id)}


@router.delete("/profile/feedback-learning/rule")
def reset_feedback_learning_rule(
    request: FeedbackLearningRuleReset,
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user),
):
    return {"success": True, "data": store.reset_feedback_learning(
        user_id=current_user.id, feature=request.feature, value=request.value
    )}


@router.get("/profile")
def get_profile(
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    return {"success": True, "profile": store.get_profile(user_id=current_user.id)}


@router.put("/profile/information-type-preferences")
def update_information_type_preferences(
    request: InformationTypePreferencesUpdate,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Persist optional choices without changing the reader's interests.

    A normal Engine backfill request is deduplicated by the existing runtime;
    this endpoint never calls a collector or an external provider itself.
    """
    profile = OnboardingService(store).update_information_type_preferences(
        request.interest_type_preferences, user_id=current_user.id
    )
    from src.engine.operations import get_engine_operations

    runtime = get_engine_operations()
    queued = runtime.request_user_backfill(current_user.id, "information_type_preferences") if runtime else 0
    return {"success": True, "profile": profile, "queued_collection_jobs": queued}


@router.get("/onboarding/status")
def onboarding_status(
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    """The authoritative, per-user route decision for first-run navigation."""
    settings = store.get_settings(user_id=current_user.id)
    return {"success": True, "completed": bool(settings.get("onboarding_completed"))}


@router.post("/onboarding/preview")
def onboarding_preview(
    request: OnboardingPreviewRequest,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Read-only routing/availability preview for the onboarding form.

    This never enqueues collection, contacts an external source, or changes a
    profile. It lets the form be honest about an unavailable information type
    before the user completes onboarding.
    """
    keywords = OnboardingService(store)._normalize_terms(request.keywords)
    preferences = OnboardingService(store)._normalize_type_preferences(
        request.interest_type_preferences, keywords
    )
    profile = {"raw_onboarding_json": {"interest_type_preferences": preferences}}
    source_configs = store.get_source_configs(user_id=current_user.id)
    approved_sources = EngineConfig.from_env().collection.pilot_sources
    router_service = SourceRouter()
    interests = []
    for keyword in keywords:
        categories = router_service.classify_interests(profile, [{"keyword": keyword, "status": "active"}])
        support = collection_support(keyword, approved_sources, source_configs, profile=profile)
        clarification = clarification_for_interest(keyword)
        interests.append({
            "keyword": keyword,
            "categories": sorted(categories),
            "information_type_options": clarification["options"] if clarification else options_for_categories(categories),
            "clarification": clarification or {"needed": False, "options": []},
            "availability": _availability_for(support),
        })
    return {"success": True, "interests": interests}


def _availability_for(support):
    status = support.get("status")
    states = {item.get("state") for item in support.get("source_states", {}).values()}
    source_ids = sorted(str(source_id) for source_id in (support.get("source_states") or {}))
    if status == "supported":
        return {
            "state": "briefing_possible",
            "can_generate_initial_briefing": True,
            "operational_source_ids": list(support.get("sources") or []),
            "message": "현재 운영 정보원으로 첫 브리핑을 준비할 수 있어요. 이번 기간의 새 소식은 수집 뒤 확인됩니다.",
        }
    if "permission_review" in states or status == "awaiting_approved_source":
        return {
            "state": "permission_review",
            "can_generate_initial_briefing": False,
            "pending_source_ids": source_ids,
            "message": "현재 카드에 사용할 운영 정보원은 없어요. 관련 정보원의 이용권한과 운영 조건을 확인 중이에요.",
        }
    if status in {"awaiting_configuration", "awaiting_runtime_approval"}:
        return {
            "state": "source_setup_pending",
            "can_generate_initial_briefing": False,
            "pending_source_ids": source_ids,
            "message": "정보원 연결과 운영 설정을 준비하고 있어요.",
        }
    return {
        "state": "no_compatible_source",
        "can_generate_initial_briefing": False,
        "pending_source_ids": source_ids,
        "message": "이 관심사와 정보 유형에 맞는 운영 정보원을 준비하고 있어요.",
    }


@router.post("/onboarding")
def save_onboarding(
    request: OnboardingRequest,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    result = OnboardingService(store).save(request.dict(), user_id=current_user.id)
    from src.engine.operations import get_engine_operations
    runtime = get_engine_operations()
    if runtime is not None:
        result["queued_collection_jobs"] = runtime.request_user_backfill(current_user.id, "onboarding")
    return {"success": True, "data": result}

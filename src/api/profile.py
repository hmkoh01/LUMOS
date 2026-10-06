from fastapi import APIRouter, Depends

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.models import OnboardingRequest
from src.context.onboarding import OnboardingService
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["profile"])


@router.get("/profile")
def get_profile(
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    return {"success": True, "profile": store.get_profile(user_id=current_user.id)}


@router.post("/onboarding")
def save_onboarding(
    request: OnboardingRequest,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    result = OnboardingService(store).save(request.dict(), user_id=current_user.id)
    return {"success": True, "data": result}

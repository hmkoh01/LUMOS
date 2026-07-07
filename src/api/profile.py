from fastapi import APIRouter, Depends

from src.api.dependencies import get_store
from src.api.models import OnboardingRequest
from src.context.onboarding import OnboardingService
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["profile"])


@router.get("/profile")
def get_profile(store: SQLiteStore = Depends(get_store)):
    return {"success": True, "profile": store.get_profile()}


@router.post("/onboarding")
def save_onboarding(request: OnboardingRequest, store: SQLiteStore = Depends(get_store)):
    result = OnboardingService(store).save(request.dict())
    return {"success": True, "data": result}


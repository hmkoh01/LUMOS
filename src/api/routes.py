from fastapi import APIRouter

from src.api.collection import router as collection_router
from src.api.connectors import router as connectors_router
from src.api.context import router as context_router
from src.api.feedback import router as feedback_router
from src.api.profile import router as profile_router
from src.api.product_cloud import router as product_cloud_router
from src.api.product_gates import router as product_gates_router
from src.api.pipeline_runs import router as pipeline_runs_router
from src.api.routes_preview import router as routes_preview_router
from src.api.settings import router as settings_router
from src.api.signals import router as signals_router
from src.api.sources import router as sources_router

router = APIRouter(prefix="/api/v1")
router.include_router(settings_router)
router.include_router(profile_router)
router.include_router(product_cloud_router)
router.include_router(product_gates_router)
router.include_router(connectors_router)
router.include_router(context_router)
router.include_router(routes_preview_router)
router.include_router(collection_router)
router.include_router(signals_router)
router.include_router(feedback_router)
router.include_router(pipeline_runs_router)
router.include_router(sources_router)

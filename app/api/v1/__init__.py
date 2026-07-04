from fastapi import APIRouter

from app.api.v1.chat import router as chat_router
from app.api.v1.models import router as models_router

router = APIRouter()
router.include_router(chat_router)
router.include_router(models_router)

__all__ = ["router"]

from fastapi import APIRouter, Depends

from app.api.deps import get_registry
from app.router.registry import ModelRegistry
from app.schemas import ModelListItem, ModelListResponse

router = APIRouter(prefix="/v1", tags=["models"])


@router.get("/models", response_model=ModelListResponse)
async def list_models(
    registry: ModelRegistry = Depends(get_registry),
) -> ModelListResponse:
    return ModelListResponse(
        data=[ModelListItem(id=model_id) for model_id in registry.list_logical_models()]
    )

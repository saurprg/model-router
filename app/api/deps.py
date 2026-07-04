from fastapi import Request

from app.middleware.request_id import get_request_id as _get_request_id_from_middleware
from app.router.registry import ModelRegistry


def get_request_id(request: Request) -> str:
    return _get_request_id_from_middleware(request)


def get_registry(request: Request) -> ModelRegistry:
    return request.app.state.registry

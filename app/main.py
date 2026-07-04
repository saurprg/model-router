from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request

from app.api.deps import get_request_id
from app.api.v1 import router as v1_router
from app.api.v1.chat import run_chat_completion
from app.errors import register_exception_handlers
from app.logging_config import configure_logging
from app.middleware import RequestIdMiddleware
from app.orchestrator import FallbackOrchestrator
from app.router.health import ProviderHealth
from app.router.registry import get_registry
from app.schemas import ChatCompletionRequest
from app.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=settings.connect_timeout_s,
            read=settings.read_timeout_s,
            write=settings.read_timeout_s,
            pool=settings.connect_timeout_s,
        )
    )
    app.state.registry = get_registry()
    app.state.provider_health = ProviderHealth()
    app.state.orchestrator = FallbackOrchestrator(
        registry=app.state.registry,
        http=app.state.http,
        health=app.state.provider_health,
    )
    yield
    await app.state.http.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="Model Router", lifespan=lifespan)
    register_exception_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(v1_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/debug/routes/{logical_model:path}")
    async def debug_resolve(logical_model: str, request: Request) -> dict:
        registry = request.app.state.registry
        targets = registry.resolve(logical_model)
        return {
            "logical_model": logical_model,
            "targets": [
                {"provider": target.provider, "model": target.model} for target in targets
            ],
        }

    @app.get("/debug/health/providers")
    async def debug_provider_health(request: Request) -> dict:
        health: ProviderHealth = request.app.state.provider_health
        snapshot = health.snapshot()
        return {
            "providers": {
                provider: {
                    **state,
                    "healthy": health.is_healthy(provider),
                }
                for provider, state in snapshot.items()
            }
        }

    @app.post("/debug/complete")
    async def debug_complete(body: ChatCompletionRequest, request: Request):
        return await run_chat_completion(
            body,
            request.app.state.orchestrator,
            get_request_id(request),
        )

    return app


app = create_app()

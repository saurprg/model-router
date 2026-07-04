from fastapi import Request

from app.orchestrator.fallback import FallbackOrchestrator


def get_orchestrator(request: Request) -> FallbackOrchestrator:
    return request.app.state.orchestrator


__all__ = ["FallbackOrchestrator", "get_orchestrator"]

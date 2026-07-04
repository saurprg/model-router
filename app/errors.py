from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class RouterError(Exception):
    def __init__(self, message: str, *, code: str = "router_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class RetryableError(RouterError):
    """Upstream/provider failure — orchestrator may try the next target."""


class FatalError(RouterError):
    """Client or policy error — do not fallback."""


class UnknownModelError(FatalError):
    def __init__(self, model: str) -> None:
        super().__init__(f"Unknown model: {model}", code="unknown_model")


class AllProvidersFailed(RouterError):
    def __init__(self, model: str) -> None:
        super().__init__(
            f"All providers failed for model: {model}",
            code="all_providers_failed",
        )


def error_payload(exc: RouterError) -> dict:
    return {
        "error": {
            "message": exc.message,
            "type": exc.__class__.__name__,
            "code": exc.code,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(FatalError)
    async def fatal_error_handler(_request: Request, exc: FatalError) -> JSONResponse:
        status_code = 404 if isinstance(exc, UnknownModelError) else 400
        return JSONResponse(status_code=status_code, content=error_payload(exc))

    @app.exception_handler(AllProvidersFailed)
    async def all_providers_failed_handler(
        _request: Request, exc: AllProvidersFailed
    ) -> JSONResponse:
        return JSONResponse(status_code=502, content=error_payload(exc))

    @app.exception_handler(RouterError)
    async def router_error_handler(_request: Request, exc: RouterError) -> JSONResponse:
        return JSONResponse(status_code=500, content=error_payload(exc))

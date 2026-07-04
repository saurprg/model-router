from __future__ import annotations

from typing import AsyncIterator, Protocol

import httpx

from app.errors import FatalError, RetryableError, RouterError
from app.router.registry import RouteTarget
from app.schemas import ChatCompletionChunk, ChatCompletionRequest, ChatCompletionResponse


class ProviderAdapter(Protocol):
    provider_name: str

    async def complete(
        self, request: ChatCompletionRequest, target: RouteTarget
    ) -> ChatCompletionResponse: ...

    async def stream(
        self, request: ChatCompletionRequest, target: RouteTarget
    ) -> AsyncIterator[ChatCompletionChunk]: ...


def map_http_error(status_code: int, body: str = "") -> RouterError:
    message = body.strip() or f"Upstream HTTP {status_code}"
    if status_code == 400:
        return FatalError(message, code="upstream_bad_request")
    if status_code in (401, 403, 429, 502, 503, 504):
        return RetryableError(message, code=f"upstream_{status_code}")
    return RetryableError(message, code="upstream_error")


def map_transport_error(exc: Exception) -> RouterError:
    if isinstance(exc, httpx.TimeoutException):
        return RetryableError("Upstream timeout", code="upstream_timeout")
    if isinstance(exc, httpx.RequestError):
        return RetryableError(str(exc), code="upstream_connection_error")
    return RetryableError(str(exc), code="upstream_error")

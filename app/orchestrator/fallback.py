from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator

import httpx

from app.errors import AllProvidersFailed, FatalError, RetryableError
from app.logging_config import log_event
from app.orchestrator.results import CompletionResult, StreamResult
from app.providers import get_adapter
from app.router.health import ProviderHealth
from app.router.registry import ModelRegistry, RouteTarget
from app.schemas import ChatCompletionChunk, ChatCompletionRequest

logger = logging.getLogger(__name__)


class FallbackOrchestrator:
    def __init__(
        self,
        registry: ModelRegistry,
        http: httpx.AsyncClient,
        health: ProviderHealth | None = None,
    ) -> None:
        self._registry = registry
        self._http = http
        self._health = health or ProviderHealth()

    async def execute(
        self, request: ChatCompletionRequest, request_id: str
    ) -> CompletionResult:
        targets = self._registry.resolve(request.model)

        for attempt, target in enumerate(targets, start=1):
            if not self._health.is_healthy(target.provider):
                self._log_attempt(
                    request_id=request_id,
                    logical_model=request.model,
                    target=target,
                    attempt=attempt,
                    outcome="skip_unhealthy",
                    latency_ms=0,
                    error_code="provider_unhealthy",
                )
                continue

            adapter = get_adapter(target.provider, self._http, self._registry)
            started = time.perf_counter()
            try:
                response = await adapter.complete(request, target)
                latency_ms = self._elapsed_ms(started)
                self._health.record_success(target.provider)
                self._log_attempt(
                    request_id=request_id,
                    logical_model=request.model,
                    target=target,
                    attempt=attempt,
                    outcome="success",
                    latency_ms=latency_ms,
                )
                return CompletionResult(
                    response=response,
                    routed_provider=target.provider,
                    upstream_model=target.model,
                )
            except RetryableError as exc:
                latency_ms = self._elapsed_ms(started)
                self._health.record_failure(target.provider)
                self._log_attempt(
                    request_id=request_id,
                    logical_model=request.model,
                    target=target,
                    attempt=attempt,
                    outcome="retry",
                    latency_ms=latency_ms,
                    error_code=exc.code,
                )
                continue
            except FatalError as exc:
                latency_ms = self._elapsed_ms(started)
                self._log_attempt(
                    request_id=request_id,
                    logical_model=request.model,
                    target=target,
                    attempt=attempt,
                    outcome="fail_fatal",
                    latency_ms=latency_ms,
                    error_code=exc.code,
                )
                raise

        raise AllProvidersFailed(request.model)

    async def execute_stream(
        self, request: ChatCompletionRequest, request_id: str
    ) -> StreamResult:
        targets = self._registry.resolve(request.model)

        for attempt, target in enumerate(targets, start=1):
            if not self._health.is_healthy(target.provider):
                self._log_attempt(
                    request_id=request_id,
                    logical_model=request.model,
                    target=target,
                    attempt=attempt,
                    outcome="skip_unhealthy",
                    latency_ms=0,
                    error_code="provider_unhealthy",
                )
                continue

            adapter = get_adapter(target.provider, self._http, self._registry)
            started = time.perf_counter()
            try:
                stream = adapter.stream(request, target)
                first_chunk: ChatCompletionChunk | None = None
                async for chunk in stream:
                    first_chunk = chunk
                    break

                if first_chunk is None:
                    latency_ms = self._elapsed_ms(started)
                    self._health.record_success(target.provider)
                    self._log_attempt(
                        request_id=request_id,
                        logical_model=request.model,
                        target=target,
                        attempt=attempt,
                        outcome="success",
                        latency_ms=latency_ms,
                    )

                    async def empty_stream() -> AsyncIterator[ChatCompletionChunk]:
                        for _ in ():
                            yield _

                    return StreamResult(
                        routed_provider=target.provider,
                        upstream_model=target.model,
                        chunks=empty_stream(),
                    )

                async def relay() -> AsyncIterator[ChatCompletionChunk]:
                    yield first_chunk
                    async for chunk in stream:
                        yield chunk
                    self._health.record_success(target.provider)
                    self._log_attempt(
                        request_id=request_id,
                        logical_model=request.model,
                        target=target,
                        attempt=attempt,
                        outcome="success",
                        latency_ms=self._elapsed_ms(started),
                    )

                return StreamResult(
                    routed_provider=target.provider,
                    upstream_model=target.model,
                    chunks=relay(),
                )
            except RetryableError as exc:
                latency_ms = self._elapsed_ms(started)
                self._health.record_failure(target.provider)
                self._log_attempt(
                    request_id=request_id,
                    logical_model=request.model,
                    target=target,
                    attempt=attempt,
                    outcome="retry",
                    latency_ms=latency_ms,
                    error_code=exc.code,
                )
                continue
            except FatalError as exc:
                latency_ms = self._elapsed_ms(started)
                self._log_attempt(
                    request_id=request_id,
                    logical_model=request.model,
                    target=target,
                    attempt=attempt,
                    outcome="fail_fatal",
                    latency_ms=latency_ms,
                    error_code=exc.code,
                )
                raise

        raise AllProvidersFailed(request.model)

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    @staticmethod
    def _log_attempt(
        *,
        request_id: str,
        logical_model: str,
        target: RouteTarget,
        attempt: int,
        outcome: str,
        latency_ms: int,
        error_code: str | None = None,
    ) -> None:
        fields: dict[str, object] = {
            "request_id": request_id,
            "logical_model": logical_model,
            "provider": target.provider,
            "upstream_model": target.model,
            "attempt": attempt,
            "latency_ms": latency_ms,
            "outcome": outcome,
        }
        if error_code is not None:
            fields["error_code"] = error_code
        log_event(logger, "inference_attempt", **fields)

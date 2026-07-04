from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.errors import AllProvidersFailed, FatalError, RetryableError
from app.orchestrator.fallback import FallbackOrchestrator
from app.router.registry import ModelRegistry, RouteTarget
from app.schemas import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Delta,
    StreamChoice,
)


class FakeAdapter:
    provider_name = "fake"

    def __init__(
        self,
        *,
        complete_result: ChatCompletionResponse | None = None,
        complete_error: Exception | None = None,
        stream_chunks: list[ChatCompletionChunk] | None = None,
        stream_error: Exception | None = None,
        stream_error_after: int | None = None,
    ) -> None:
        self.complete_result = complete_result
        self.complete_error = complete_error
        self.stream_chunks = stream_chunks or []
        self.stream_error = stream_error
        self.stream_error_after = stream_error_after
        self.complete_calls = 0
        self.stream_calls = 0

    async def complete(
        self, request: ChatCompletionRequest, target: RouteTarget
    ) -> ChatCompletionResponse:
        self.complete_calls += 1
        if self.complete_error:
            raise self.complete_error
        assert self.complete_result is not None
        return self.complete_result

    async def stream(
        self, request: ChatCompletionRequest, target: RouteTarget
    ) -> AsyncIterator[ChatCompletionChunk]:
        self.stream_calls += 1
        if self.stream_error and self.stream_error_after is None and not self.stream_chunks:
            raise self.stream_error

        yielded = 0
        for chunk in self.stream_chunks:
            yield chunk
            yielded += 1
            if (
                self.stream_error
                and self.stream_error_after is not None
                and yielded >= self.stream_error_after
            ):
                raise self.stream_error

        if self.stream_error and self.stream_error_after is None:
            raise self.stream_error


def _response(model: str, content: str = "ok") -> ChatCompletionResponse:
    return ChatCompletionResponse(
        id="cmpl-1",
        model=model,
        choices=[
            ChatCompletionChoice(
                message=ChatMessage(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
    )


def _chunk(content: str) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id="chunk-1",
        choices=[StreamChoice(index=0, delta=Delta(content=content))],
    )


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry(Path("config/models.yaml"))


@pytest.fixture
def orchestrator(registry: ModelRegistry) -> FallbackOrchestrator:
    return FallbackOrchestrator(registry=registry, http=httpx.AsyncClient())


@pytest.fixture
def request_body() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="smart/general",
        messages=[ChatMessage(role="user", content="Hi")],
    )


@pytest.mark.asyncio
async def test_execute_primary_success(
    orchestrator: FallbackOrchestrator,
    request_body: ChatCompletionRequest,
) -> None:
    adapter = FakeAdapter(
        complete_result=_response("llama-3.1-8b-instant", content="primary")
    )

    with patch(
        "app.orchestrator.fallback.get_adapter",
        return_value=adapter,
    ):
        result = await orchestrator.execute(request_body, "req-1")

    assert result.response.choices[0].message.content == "primary"
    assert result.routed_provider == "groq"
    assert adapter.complete_calls == 1


@pytest.mark.asyncio
async def test_execute_falls_back_on_retryable(
    orchestrator: FallbackOrchestrator,
    request_body: ChatCompletionRequest,
) -> None:
    primary = FakeAdapter(
        complete_error=RetryableError("upstream 503", code="upstream_503")
    )
    fallback = FakeAdapter(
        complete_result=_response("llama3.3-70b-instruct", content="fallback")
    )
    adapters = iter([primary, fallback])

    with patch(
        "app.orchestrator.fallback.get_adapter",
        side_effect=lambda *_args, **_kwargs: next(adapters),
    ):
        result = await orchestrator.execute(request_body, "req-2")

    assert result.response.choices[0].message.content == "fallback"
    assert result.response.model == "llama3.3-70b-instruct"
    assert result.routed_provider == "digitalocean"
    assert primary.complete_calls == 1
    assert fallback.complete_calls == 1


@pytest.mark.asyncio
async def test_execute_fatal_error_no_fallback(
    orchestrator: FallbackOrchestrator,
    request_body: ChatCompletionRequest,
) -> None:
    primary = FakeAdapter(
        complete_error=FatalError("bad request", code="upstream_bad_request")
    )
    fallback = FakeAdapter(complete_result=_response("llama3.3-70b-instruct"))
    adapters = iter([primary, fallback])

    with patch(
        "app.orchestrator.fallback.get_adapter",
        side_effect=lambda *_args, **_kwargs: next(adapters),
    ):
        with pytest.raises(FatalError):
            await orchestrator.execute(request_body, "req-3")

    assert primary.complete_calls == 1
    assert fallback.complete_calls == 0


@pytest.mark.asyncio
async def test_execute_all_providers_failed(
    orchestrator: FallbackOrchestrator,
    request_body: ChatCompletionRequest,
) -> None:
    with patch(
        "app.orchestrator.fallback.get_adapter",
        return_value=FakeAdapter(
            complete_error=RetryableError("upstream 503", code="upstream_503")
        ),
    ):
        with pytest.raises(AllProvidersFailed):
            await orchestrator.execute(request_body, "req-4")


@pytest.mark.asyncio
async def test_stream_falls_back_before_first_chunk(
    orchestrator: FallbackOrchestrator,
    request_body: ChatCompletionRequest,
) -> None:
    request_body.stream = True
    primary = FakeAdapter(
        stream_error=RetryableError("upstream 503", code="upstream_503")
    )
    fallback = FakeAdapter(stream_chunks=[_chunk("hello")])
    adapters = iter([primary, fallback])

    with patch(
        "app.orchestrator.fallback.get_adapter",
        side_effect=lambda *_args, **_kwargs: next(adapters),
    ):
        stream = await orchestrator.execute_stream(request_body, "req-5")
        chunks = [chunk async for chunk in stream.chunks]

    assert len(chunks) == 1
    assert chunks[0].choices[0].delta.content == "hello"
    assert primary.stream_calls == 1
    assert fallback.stream_calls == 1


@pytest.mark.asyncio
async def test_stream_no_fallback_after_first_chunk(
    orchestrator: FallbackOrchestrator,
    request_body: ChatCompletionRequest,
) -> None:
    request_body.stream = True
    primary = FakeAdapter(
        stream_chunks=[_chunk("partial")],
        stream_error=RetryableError("upstream reset", code="upstream_error"),
        stream_error_after=1,
    )
    fallback = FakeAdapter(stream_chunks=[_chunk("fallback")])
    adapters = iter([primary, fallback])
    get_adapter_mock = MagicMock(side_effect=lambda *_args, **_kwargs: next(adapters))

    with patch("app.orchestrator.fallback.get_adapter", get_adapter_mock):
        stream = await orchestrator.execute_stream(request_body, "req-6")
        with pytest.raises(RetryableError):
            async for _ in stream.chunks:
                pass

    assert primary.stream_calls == 1
    assert fallback.stream_calls == 0
    assert get_adapter_mock.call_count == 1


@pytest.mark.asyncio
async def test_stream_empty_response_succeeds(
    orchestrator: FallbackOrchestrator,
    request_body: ChatCompletionRequest,
) -> None:
    request_body.stream = True
    adapter = FakeAdapter(stream_chunks=[])

    with patch("app.orchestrator.fallback.get_adapter", return_value=adapter):
        stream = await orchestrator.execute_stream(request_body, "req-empty")
        chunks = [chunk async for chunk in stream.chunks]

    assert chunks == []
    assert stream.routed_provider == "groq"
    assert adapter.stream_calls == 1


@pytest.mark.asyncio
async def test_stream_fatal_error_before_first_chunk_no_fallback(
    orchestrator: FallbackOrchestrator,
    request_body: ChatCompletionRequest,
) -> None:
    request_body.stream = True
    primary = FakeAdapter(
        stream_error=FatalError("bad request", code="upstream_bad_request")
    )
    fallback = FakeAdapter(stream_chunks=[_chunk("fallback")])
    adapters = iter([primary, fallback])

    with patch(
        "app.orchestrator.fallback.get_adapter",
        side_effect=lambda *_args, **_kwargs: next(adapters),
    ):
        with pytest.raises(FatalError):
            await orchestrator.execute_stream(request_body, "req-fatal-stream")

    assert primary.stream_calls == 1
    assert fallback.stream_calls == 0

import httpx
import pytest
import respx

from app.errors import FatalError, RetryableError
from app.providers.openai_adapter import OpenAIAdapter
from app.router.registry import ProviderConfig, RouteTarget
from app.schemas import ChatCompletionRequest, ChatMessage


@pytest.fixture
def groq_adapter() -> OpenAIAdapter:
    return OpenAIAdapter(
        http=httpx.AsyncClient(),
        provider_config=ProviderConfig(
            base_url="https://api.groq.com/openai/v1",
            api_key_env="GROQ_API_KEY",
        ),
    )


@pytest.fixture
def target() -> RouteTarget:
    return RouteTarget(provider="groq", model="llama-3.1-8b-instant")


@pytest.fixture
def request_body() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="fast/demo",
        messages=[ChatMessage(role="user", content="Hi")],
    )


@pytest.mark.asyncio
@respx.mock
async def test_complete_success(
    groq_adapter: OpenAIAdapter,
    target: RouteTarget,
    request_body: ChatCompletionRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "cmpl-1",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )
    )

    response = await groq_adapter.complete(request_body, target)
    assert response.choices[0].message.content == "Hello"
    assert response.model == "llama-3.1-8b-instant"


@pytest.mark.asyncio
@respx.mock
async def test_complete_upstream_401_raises_retryable(
    groq_adapter: OpenAIAdapter,
    target: RouteTarget,
    request_body: ChatCompletionRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )

    with pytest.raises(RetryableError):
        await groq_adapter.complete(request_body, target)


@pytest.mark.asyncio
@respx.mock
async def test_complete_upstream_400_raises_fatal(
    groq_adapter: OpenAIAdapter,
    target: RouteTarget,
    request_body: ChatCompletionRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(400, text="Bad request")
    )

    with pytest.raises(FatalError):
        await groq_adapter.complete(request_body, target)


@pytest.mark.asyncio
async def test_missing_api_key_raises_retryable(
    groq_adapter: OpenAIAdapter,
    target: RouteTarget,
    request_body: ChatCompletionRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(RetryableError) as exc:
        await groq_adapter.complete(request_body, target)
    assert exc.value.code == "missing_api_key"


@pytest.mark.asyncio
@respx.mock
async def test_complete_upstream_429_raises_retryable(
    groq_adapter: OpenAIAdapter,
    target: RouteTarget,
    request_body: ChatCompletionRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(429, text="Rate limited")
    )

    with pytest.raises(RetryableError) as exc:
        await groq_adapter.complete(request_body, target)
    assert exc.value.code == "upstream_429"


@pytest.mark.asyncio
@respx.mock
async def test_complete_transport_error_raises_retryable(
    groq_adapter: OpenAIAdapter,
    target: RouteTarget,
    request_body: ChatCompletionRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(RetryableError) as exc:
        await groq_adapter.complete(request_body, target)
    assert exc.value.code == "upstream_connection_error"


@pytest.mark.asyncio
@respx.mock
async def test_complete_includes_optional_fields_in_payload(
    groq_adapter: OpenAIAdapter,
    target: RouteTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "cmpl-1",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )
    )
    body = ChatCompletionRequest(
        model="fast/demo",
        messages=[ChatMessage(role="user", content="Hi")],
        temperature=0.5,
        max_tokens=10,
    )

    await groq_adapter.complete(body, target)

    payload = route.calls.last.request.content
    assert payload is not None
    import json

    sent = json.loads(payload)
    assert sent["temperature"] == 0.5
    assert sent["max_tokens"] == 10
    assert sent["model"] == target.model


@pytest.mark.asyncio
async def test_stream_yields_parsed_chunks(
    groq_adapter: OpenAIAdapter,
    target: RouteTarget,
    request_body: ChatCompletionRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    request_body.stream = True

    lines = [
        'data: {"id":"c1","choices":[{"index":0,"delta":{"content":"Hi"}}]}',
        "data: [DONE]",
    ]

    class MockResponse:
        status_code = 200

        async def aread(self) -> bytes:
            return b""

        async def aiter_lines(self):
            for line in lines:
                yield line

    class MockStream:
        async def __aenter__(self):
            return MockResponse()

        async def __aexit__(self, *_args):
            return None

    groq_adapter._http.stream = lambda *args, **kwargs: MockStream()  # type: ignore[method-assign, assignment]

    chunks = [chunk async for chunk in groq_adapter.stream(request_body, target)]
    assert len(chunks) == 1
    assert chunks[0].choices[0].delta.content == "Hi"


@pytest.mark.asyncio
async def test_stream_upstream_error_before_first_chunk(
    groq_adapter: OpenAIAdapter,
    target: RouteTarget,
    request_body: ChatCompletionRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    request_body.stream = True

    class MockResponse:
        status_code = 503

        async def aread(self) -> bytes:
            return b"Service unavailable"

    class MockStream:
        async def __aenter__(self):
            return MockResponse()

        async def __aexit__(self, *_args):
            return None

    groq_adapter._http.stream = lambda *args, **kwargs: MockStream()  # type: ignore[method-assign, assignment]

    with pytest.raises(RetryableError) as exc:
        async for _ in groq_adapter.stream(request_body, target):
            pass
    assert exc.value.code == "upstream_503"

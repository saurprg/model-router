from pathlib import Path

import httpx
import pytest
import respx

from app.errors import FatalError, RetryableError
from app.providers.openai_adapter import OpenAIAdapter
from app.router.registry import ModelRegistry, ProviderConfig, RouteTarget
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

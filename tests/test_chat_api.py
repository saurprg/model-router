from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.orchestrator import get_orchestrator
from app.orchestrator.fallback import FallbackOrchestrator
from app.orchestrator.results import CompletionResult, StreamResult
from app.schemas import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionResponse,
    ChatMessage,
    Delta,
    StreamChoice,
)


def _response() -> ChatCompletionResponse:
    return ChatCompletionResponse(
        id="cmpl-test",
        model="llama-3.1-8b-instant",
        choices=[
            ChatCompletionChoice(
                message=ChatMessage(role="assistant", content="Hello"),
                finish_reason="stop",
            )
        ],
    )


async def _stream_chunks() -> AsyncIterator[ChatCompletionChunk]:
    yield ChatCompletionChunk(
        id="chunk-1",
        choices=[StreamChoice(index=0, delta=Delta(content="Hi"))],
    )


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    mock = MagicMock(spec=FallbackOrchestrator)
    mock.execute = AsyncMock(
        return_value=CompletionResult(
            response=_response(),
            routed_provider="groq",
            upstream_model="llama-3.1-8b-instant",
        )
    )

    async def _execute_stream(_request, _request_id):
        return StreamResult(
            routed_provider="groq",
            upstream_model="llama-3.1-8b-instant",
            chunks=_stream_chunks(),
        )

    mock.execute_stream = AsyncMock(side_effect=_execute_stream)
    return mock


@pytest.fixture
def client(mock_orchestrator: MagicMock) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_chat_completions_non_stream(
    client: TestClient, mock_orchestrator: MagicMock
) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "fast/demo",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["choices"][0]["message"]["content"] == "Hello"
    assert response.headers["X-Routed-Provider"] == "groq"
    mock_orchestrator.execute.assert_awaited_once()


def test_chat_completions_stream(client: TestClient, mock_orchestrator: MagicMock) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "fast/demo",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert response.headers["X-Routed-Provider"] == "groq"
    assert "data: [DONE]" in response.text
    assert '"content":"Hi"' in response.text
    mock_orchestrator.execute.assert_not_called()


def test_list_models(client: TestClient) -> None:
    response = client.get("/v1/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "list"
    model_ids = [item["id"] for item in payload["data"]]
    assert "smart/general" in model_ids
    assert model_ids == sorted(model_ids)


def test_unknown_model_404() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "nope",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": False,
            },
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_model"

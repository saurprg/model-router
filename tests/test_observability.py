import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.errors import AllProvidersFailed, RetryableError
from app.main import create_app
from app.middleware import REQUEST_ID_HEADER
from app.orchestrator import get_orchestrator
from app.orchestrator.fallback import FallbackOrchestrator
from app.orchestrator.results import CompletionResult
from app.providers.openai_adapter import OpenAIAdapter
from app.router.registry import ModelRegistry, ProviderConfig
from app.schemas import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)


def test_x_request_id_on_response() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert REQUEST_ID_HEADER in response.headers
    assert response.headers[REQUEST_ID_HEADER]


def test_x_request_id_echoes_inbound() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health", headers={REQUEST_ID_HEADER: "test-trace-123"})

    assert response.headers[REQUEST_ID_HEADER] == "test-trace-123"


def test_x_routed_provider_on_success() -> None:
    mock = MagicMock(spec=FallbackOrchestrator)
    mock.execute = AsyncMock(
        return_value=CompletionResult(
            response=ChatCompletionResponse(
                id="cmpl-1",
                model="llama-3.1-8b-instant",
                choices=[
                    ChatCompletionChoice(
                        message=ChatMessage(role="assistant", content="Hi"),
                        finish_reason="stop",
                    )
                ],
            ),
            routed_provider="groq",
            upstream_model="llama-3.1-8b-instant",
        )
    )

    app = create_app()
    app.dependency_overrides[get_orchestrator] = lambda: mock
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "fast/demo",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": False,
            },
        )

    assert response.status_code == 200
    assert response.headers["X-Routed-Provider"] == "groq"


@pytest.mark.asyncio
async def test_structured_log_on_retry(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="app.orchestrator.fallback")

    adapter = OpenAIAdapter(
        http=MagicMock(),
        provider_config=ProviderConfig(
            base_url="https://api.groq.com/openai/v1",
            api_key_env="GROQ_API_KEY",
        ),
    )

    async def _fail(*_args, **_kwargs):
        raise RetryableError("upstream 503", code="upstream_503")

    monkeypatch.setattr(adapter, "complete", _fail)

    from pathlib import Path

    orchestrator = FallbackOrchestrator(
        registry=ModelRegistry(Path("config/models.yaml")),
        http=httpx.AsyncClient(),
    )
    request = ChatCompletionRequest(
        model="fast/demo",
        messages=[ChatMessage(role="user", content="Hi")],
    )

    with patch("app.orchestrator.fallback.get_adapter", return_value=adapter):
        with pytest.raises(AllProvidersFailed):
            await orchestrator.execute(request, "req-log-1")

    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.message.startswith("{")
    ]
    retry_events = [event for event in records if event.get("outcome") == "retry"]
    assert len(retry_events) == 1
    assert retry_events[0]["request_id"] == "req-log-1"
    assert retry_events[0]["provider"] == "groq"
    assert "latency_ms" in retry_events[0]


@pytest.mark.asyncio
async def test_structured_log_on_success(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging
    from pathlib import Path

    caplog.set_level(logging.INFO, logger="app.orchestrator.fallback")

    adapter = OpenAIAdapter(
        http=MagicMock(),
        provider_config=ProviderConfig(
            base_url="https://api.groq.com/openai/v1",
            api_key_env="GROQ_API_KEY",
        ),
    )

    async def _ok(*_args, **_kwargs):
        return ChatCompletionResponse(
            id="cmpl-1",
            model="llama-3.1-8b-instant",
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(role="assistant", content="Hi"),
                    finish_reason="stop",
                )
            ],
        )

    monkeypatch.setattr(adapter, "complete", _ok)

    orchestrator = FallbackOrchestrator(
        registry=ModelRegistry(Path("config/models.yaml")),
        http=httpx.AsyncClient(),
    )
    request = ChatCompletionRequest(
        model="fast/demo",
        messages=[ChatMessage(role="user", content="Hi")],
    )

    with patch("app.orchestrator.fallback.get_adapter", return_value=adapter):
        await orchestrator.execute(request, "req-log-success")

    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.message.startswith("{")
    ]
    success = [event for event in records if event.get("outcome") == "success"]
    assert len(success) == 1
    assert success[0]["request_id"] == "req-log-success"


@pytest.mark.asyncio
async def test_structured_log_on_skip_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging
    from pathlib import Path

    from app.router.health import ProviderHealth

    caplog.set_level(logging.INFO, logger="app.orchestrator.fallback")

    health = ProviderHealth(failure_threshold=1)
    health.record_failure("groq")

    orchestrator = FallbackOrchestrator(
        registry=ModelRegistry(Path("config/models.yaml")),
        http=httpx.AsyncClient(),
        health=health,
    )
    adapter = OpenAIAdapter(
        http=MagicMock(),
        provider_config=ProviderConfig(
            base_url="https://api.groq.com/openai/v1",
            api_key_env="GROQ_API_KEY",
        ),
    )

    async def _ok(*_args, **_kwargs):
        return ChatCompletionResponse(
            id="cmpl-1",
            model="llama-3.1-8b-instant",
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(role="assistant", content="Hi"),
                    finish_reason="stop",
                )
            ],
        )

    monkeypatch.setattr(adapter, "complete", _ok)

    request = ChatCompletionRequest(
        model="fast/demo",
        messages=[ChatMessage(role="user", content="Hi")],
    )

    with patch("app.orchestrator.fallback.get_adapter", return_value=adapter):
        with pytest.raises(AllProvidersFailed):
            await orchestrator.execute(request, "req-log-skip")

    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.message.startswith("{")
    ]
    skipped = [event for event in records if event.get("outcome") == "skip_unhealthy"]
    assert len(skipped) == 1
    assert skipped[0]["error_code"] == "provider_unhealthy"

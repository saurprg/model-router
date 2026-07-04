from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.errors import AllProvidersFailed, RetryableError
from app.orchestrator.fallback import FallbackOrchestrator
from app.router.health import ProviderHealth
from app.router.registry import ModelRegistry
from app.schemas import ChatCompletionRequest, ChatMessage
from tests.test_fallback import FakeAdapter, _response


def test_starts_healthy() -> None:
    health = ProviderHealth()
    assert health.is_healthy("groq") is True


def test_three_failures_opens_circuit() -> None:
    health = ProviderHealth(failure_threshold=3, recovery_seconds=60.0)

    health.record_failure("groq")
    health.record_failure("groq")
    assert health.is_healthy("groq") is True

    health.record_failure("groq")
    assert health.is_healthy("groq") is False


def test_success_resets_failures() -> None:
    health = ProviderHealth(failure_threshold=3)

    health.record_failure("groq")
    health.record_failure("groq")
    health.record_success("groq")

    assert health.is_healthy("groq") is True
    assert health.snapshot()["groq"]["consecutive_failures"] == 0


def test_recovery_after_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 1000.0}
    monkeypatch.setattr("app.router.health.time.monotonic", lambda: clock["now"])

    health = ProviderHealth(failure_threshold=3, recovery_seconds=60.0)
    for _ in range(3):
        health.record_failure("groq")

    assert health.is_healthy("groq") is False

    clock["now"] = 1061.0
    assert health.is_healthy("groq") is True


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry(Path("config/models.yaml"))


@pytest.fixture
def request_body() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="smart/general",
        messages=[ChatMessage(role="user", content="Hi")],
    )


@pytest.mark.asyncio
async def test_orchestrator_skips_unhealthy_provider(
    registry: ModelRegistry,
    request_body: ChatCompletionRequest,
) -> None:
    health = ProviderHealth(failure_threshold=1, recovery_seconds=60.0)
    health.record_failure("groq")
    orchestrator = FallbackOrchestrator(
        registry=registry,
        http=httpx.AsyncClient(),
        health=health,
    )

    primary = FakeAdapter(
        complete_error=RetryableError("upstream 503", code="upstream_503")
    )
    fallback = FakeAdapter(
        complete_result=_response("llama3.3-70b-instruct", content="fallback")
    )
    providers: list[str] = []

    def _get_adapter(provider: str, *_args, **_kwargs):
        providers.append(provider)
        if provider == "groq":
            return primary
        return fallback

    with patch("app.orchestrator.fallback.get_adapter", side_effect=_get_adapter):
        result = await orchestrator.execute(request_body, "req-health-1")

    assert result.response.choices[0].message.content == "fallback"
    assert providers == ["digitalocean"]
    assert primary.complete_calls == 0


@pytest.mark.asyncio
async def test_orchestrator_records_failure_on_retryable(
    registry: ModelRegistry,
    request_body: ChatCompletionRequest,
) -> None:
    health = ProviderHealth(failure_threshold=3)
    orchestrator = FallbackOrchestrator(
        registry=registry,
        http=httpx.AsyncClient(),
        health=health,
    )
    failing = FakeAdapter(
        complete_error=RetryableError("upstream 503", code="upstream_503")
    )

    with patch("app.orchestrator.fallback.get_adapter", return_value=failing):
        with pytest.raises(AllProvidersFailed):
            await orchestrator.execute(request_body, "req-health-2")

    assert health.snapshot()["groq"]["consecutive_failures"] == 1

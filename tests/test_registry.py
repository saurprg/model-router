from pathlib import Path

import pytest

from app.errors import FatalError, UnknownModelError
from app.router.registry import ModelRegistry, RouteTarget


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry(Path("config/models.yaml"))


def test_resolve_smart_general(registry: ModelRegistry) -> None:
    targets = registry.resolve("smart/general")
    assert len(targets) == 4
    assert targets[0] == RouteTarget("groq", "llama-3.1-8b-instant")
    assert targets[1] == RouteTarget("digitalocean", "llama3.3-70b-instruct")
    assert targets[2] == RouteTarget("digitalocean", "openai-gpt-5-nano")
    assert targets[3] == RouteTarget("digitalocean", "anthropic-claude-haiku-4.5")


def test_resolve_do_llama(registry: ModelRegistry) -> None:
    targets = registry.resolve("do/llama")
    assert targets == [RouteTarget("digitalocean", "llama3.3-70b-instruct")]


def test_resolve_do_openai(registry: ModelRegistry) -> None:
    targets = registry.resolve("do/openai")
    assert targets == [RouteTarget("digitalocean", "openai-gpt-5-nano")]


def test_resolve_do_anthropic(registry: ModelRegistry) -> None:
    targets = registry.resolve("do/anthropic")
    assert targets == [RouteTarget("digitalocean", "anthropic-claude-haiku-4.5")]


def test_fast_demo_groq_only(registry: ModelRegistry) -> None:
    targets = registry.resolve("fast/demo")
    assert targets == [RouteTarget("groq", "llama-3.1-8b-instant")]


def test_unknown_model_raises(registry: ModelRegistry) -> None:
    with pytest.raises(UnknownModelError):
        registry.resolve("does/not/exist")


def test_get_provider_digitalocean(registry: ModelRegistry) -> None:
    provider = registry.get_provider("digitalocean")
    assert provider.base_url == "https://inference.do-ai.run/v1"
    assert provider.api_key_env == "DO_MODEL_ACCESS_KEY"


def test_get_provider_groq(registry: ModelRegistry) -> None:
    provider = registry.get_provider("groq")
    assert provider.base_url == "https://api.groq.com/openai/v1"
    assert provider.api_key_env == "GROQ_API_KEY"


def test_list_logical_models(registry: ModelRegistry) -> None:
    assert registry.list_logical_models() == [
        "do/anthropic",
        "do/llama",
        "do/openai",
        "fast/demo",
        "smart/general",
    ]


def test_get_provider_unknown_raises(registry: ModelRegistry) -> None:
    with pytest.raises(FatalError) as exc:
        registry.get_provider("does-not-exist")
    assert exc.value.code == "unknown_provider"

import httpx
import pytest

from app.errors import FatalError
from app.providers import get_adapter
from app.providers.openai_adapter import OpenAIAdapter
from app.router.registry import ModelRegistry


@pytest.fixture
def registry() -> ModelRegistry:
    from pathlib import Path

    return ModelRegistry(Path("config/models.yaml"))


@pytest.mark.parametrize("provider", ["groq", "openai", "digitalocean"])
def test_get_adapter_known_providers(
    registry: ModelRegistry, provider: str
) -> None:
    adapter = get_adapter(provider, httpx.AsyncClient(), registry)
    assert isinstance(adapter, OpenAIAdapter)


def test_get_adapter_unknown_provider_raises(registry: ModelRegistry) -> None:
    with pytest.raises(FatalError) as exc:
        get_adapter("unknown-vendor", httpx.AsyncClient(), registry)
    assert exc.value.code == "no_adapter"

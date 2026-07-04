import httpx

from app.errors import FatalError
from app.providers.base import ProviderAdapter
from app.providers.openai_adapter import OpenAIAdapter
from app.router.registry import ModelRegistry

_ADAPTER_CLASSES = {
    "openai": OpenAIAdapter,
    "groq": OpenAIAdapter,
    "digitalocean": OpenAIAdapter,
}


def get_adapter(
    provider: str,
    http: httpx.AsyncClient,
    registry: ModelRegistry,
) -> ProviderAdapter:
    adapter_cls = _ADAPTER_CLASSES.get(provider)
    if adapter_cls is None:
        raise FatalError(f"No adapter for provider: {provider}", code="no_adapter")

    provider_config = registry.get_provider(provider)
    return adapter_cls(http=http, provider_config=provider_config)

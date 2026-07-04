from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.errors import FatalError, UnknownModelError
from app.settings import get_settings


@dataclass(frozen=True)
class RouteTarget:
    provider: str
    model: str


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    api_key_env: str


class ModelRegistry:
    def __init__(self, config_path: Path) -> None:
        self._routes: dict[str, dict[str, Any]] = {}
        self._providers: dict[str, ProviderConfig] = {}
        self._load(config_path)

    def resolve(self, logical_model: str) -> list[RouteTarget]:
        route = self._routes.get(logical_model)
        if route is None:
            raise UnknownModelError(logical_model)

        targets = [self._to_target(route["primary"])]
        for fallback in route.get("fallbacks") or []:
            targets.append(self._to_target(fallback))
        return targets

    def get_provider(self, name: str) -> ProviderConfig:
        provider = self._providers.get(name)
        if provider is None:
            raise FatalError(f"Unknown provider: {name}", code="unknown_provider")
        return provider

    def list_logical_models(self) -> list[str]:
        return sorted(self._routes.keys())

    def _load(self, config_path: Path) -> None:
        if not config_path.is_file():
            raise ValueError(f"Models config not found: {config_path}")

        with config_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid models config: expected mapping at {config_path}")

        routes = data.get("routes")
        providers = data.get("providers")
        if not isinstance(routes, dict):
            raise ValueError("models config must contain a 'routes' mapping")
        if not isinstance(providers, dict):
            raise ValueError("models config must contain a 'providers' mapping")

        self._providers = {
            name: self._parse_provider(name, entry)
            for name, entry in providers.items()
        }

        parsed_routes: dict[str, dict[str, Any]] = {}
        for logical_model, route in routes.items():
            if not isinstance(route, dict):
                raise ValueError(f"Route '{logical_model}' must be a mapping")
            primary = self._parse_target_entry(route.get("primary"), f"{logical_model}.primary")
            fallbacks_raw = route.get("fallbacks") or []
            if not isinstance(fallbacks_raw, list):
                raise ValueError(f"Route '{logical_model}' fallbacks must be a list")
            fallbacks = [
                self._parse_target_entry(entry, f"{logical_model}.fallbacks[{index}]")
                for index, entry in enumerate(fallbacks_raw)
            ]
            self._validate_target_provider(primary, logical_model)
            for fallback in fallbacks:
                self._validate_target_provider(fallback, logical_model)
            parsed_routes[logical_model] = {"primary": primary, "fallbacks": fallbacks}

        self._routes = parsed_routes

    def _parse_provider(self, name: str, entry: Any) -> ProviderConfig:
        if not isinstance(entry, dict):
            raise ValueError(f"Provider '{name}' must be a mapping")
        base_url = entry.get("base_url")
        api_key_env = entry.get("api_key_env")
        if not base_url or not api_key_env:
            raise ValueError(
                f"Provider '{name}' must define 'base_url' and 'api_key_env'"
            )
        return ProviderConfig(base_url=str(base_url), api_key_env=str(api_key_env))

    def _parse_target_entry(self, entry: Any, label: str) -> dict[str, str]:
        if not isinstance(entry, dict):
            raise ValueError(f"Target '{label}' must be a mapping")
        provider = entry.get("provider")
        model = entry.get("model")
        if not provider or not model:
            raise ValueError(f"Target '{label}' must define 'provider' and 'model'")
        return {"provider": str(provider), "model": str(model)}

    def _validate_target_provider(self, target: dict[str, str], logical_model: str) -> None:
        if target["provider"] not in self._providers:
            raise ValueError(
                f"Route '{logical_model}' references unknown provider '{target['provider']}'"
            )

    @staticmethod
    def _to_target(entry: dict[str, str]) -> RouteTarget:
        return RouteTarget(provider=entry["provider"], model=entry["model"])


@lru_cache
def get_registry() -> ModelRegistry:
    settings = get_settings()
    return ModelRegistry(settings.models_config_path)

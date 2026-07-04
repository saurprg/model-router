from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.errors import RetryableError
from app.providers.base import map_http_error, map_transport_error
from app.router.registry import ProviderConfig, RouteTarget
from app.schemas import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Delta,
    StreamChoice,
)
from app.settings import get_provider_api_key


class OpenAIAdapter:
    """Pass-through adapter for OpenAI-compatible APIs (OpenAI, Groq)."""

    provider_name = "openai_compatible"

    def __init__(self, http: httpx.AsyncClient, provider_config: ProviderConfig) -> None:
        self._http = http
        self._provider_config = provider_config

    async def complete(
        self, request: ChatCompletionRequest, target: RouteTarget
    ) -> ChatCompletionResponse:
        payload = self._build_payload(request, target, stream=False)
        data = await self._post_json(payload)
        return self._parse_completion(data, target.model)

    async def stream(
        self, request: ChatCompletionRequest, target: RouteTarget
    ) -> AsyncIterator[ChatCompletionChunk]:
        payload = self._build_payload(request, target, stream=True)
        try:
            async with self._http.stream(
                "POST",
                self._chat_completions_url(),
                json=payload,
                headers=self._headers(),
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")
                    raise map_http_error(response.status_code, body)

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line.removeprefix("data: ").strip()
                    if data == "[DONE]":
                        break
                    chunk_data = json.loads(data)
                    yield self._parse_chunk(chunk_data)
        except RetryableError:
            raise
        except httpx.HTTPError as exc:
            raise map_transport_error(exc) from exc

    def _build_payload(
        self, request: ChatCompletionRequest, target: RouteTarget, *, stream: bool
    ) -> dict:
        payload: dict = {
            "model": target.model,
            "messages": [message.model_dump() for message in request.messages],
            "stream": stream,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        return payload

    async def _post_json(self, payload: dict) -> dict:
        try:
            response = await self._http.post(
                self._chat_completions_url(),
                json=payload,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise map_transport_error(exc) from exc

        if response.status_code >= 400:
            raise map_http_error(response.status_code, response.text)

        return response.json()

    def _headers(self) -> dict[str, str]:
        api_key = get_provider_api_key(self._provider_config.api_key_env)
        if not api_key:
            raise RetryableError(
                f"Missing API key: {self._provider_config.api_key_env}",
                code="missing_api_key",
            )
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _chat_completions_url(self) -> str:
        return f"{self._provider_config.base_url.rstrip('/')}/chat/completions"

    @staticmethod
    def _parse_completion(data: dict, upstream_model: str) -> ChatCompletionResponse:
        choice = data["choices"][0]
        return ChatCompletionResponse(
            id=data["id"],
            model=upstream_model,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(**choice["message"]),
                    finish_reason=choice.get("finish_reason"),
                )
            ],
            usage=data.get("usage"),
        )

    @staticmethod
    def _parse_chunk(data: dict) -> ChatCompletionChunk:
        choices = []
        for choice in data.get("choices", []):
            delta_raw = choice.get("delta") or {}
            choices.append(
                StreamChoice(
                    index=choice.get("index", 0),
                    delta=Delta(
                        role=delta_raw.get("role"),
                        content=delta_raw.get("content"),
                    ),
                    finish_reason=choice.get("finish_reason"),
                )
            )
        return ChatCompletionChunk(id=data["id"], choices=choices)

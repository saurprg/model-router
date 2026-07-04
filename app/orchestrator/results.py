from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.schemas import ChatCompletionChunk, ChatCompletionResponse


@dataclass(frozen=True)
class CompletionResult:
    response: ChatCompletionResponse
    routed_provider: str
    upstream_model: str


@dataclass(frozen=True)
class StreamResult:
    routed_provider: str
    upstream_model: str
    chunks: AsyncIterator[ChatCompletionChunk]

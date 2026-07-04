import json

import pytest

from app.schemas import ChatCompletionChunk, Delta, StreamChoice
from app.streaming.proxy import sse_stream


async def _collect_sse(chunks: list[ChatCompletionChunk]) -> list[str]:
    async def _iter():
        for chunk in chunks:
            yield chunk

    return [line async for line in sse_stream(_iter())]


def _chunk(content: str, *, chunk_id: str = "chunk-1") -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id=chunk_id,
        choices=[
            StreamChoice(
                index=0,
                delta=Delta(content=content),
            )
        ],
    )


@pytest.mark.asyncio
async def test_sse_stream_formats_chunks() -> None:
    lines = await _collect_sse([_chunk("Hello"), _chunk(" world")])

    assert len(lines) == 3
    assert lines[0].startswith("data: ")
    assert lines[0].endswith("\n\n")
    assert lines[1].startswith("data: ")
    assert lines[2] == "data: [DONE]\n\n"

    first = json.loads(lines[0].removeprefix("data: ").strip())
    assert first["object"] == "chat.completion.chunk"
    assert first["choices"][0]["delta"]["content"] == "Hello"


@pytest.mark.asyncio
async def test_sse_stream_empty_iterator() -> None:
    lines = await _collect_sse([])
    assert lines == ["data: [DONE]\n\n"]


@pytest.mark.asyncio
async def test_chunk_json_matches_schema() -> None:
    lines = await _collect_sse([_chunk("x")])
    payload = json.loads(lines[0].removeprefix("data: ").strip())
    assert payload["id"] == "chunk-1"
    assert payload["object"] == "chat.completion.chunk"
    assert payload["choices"][0]["index"] == 0

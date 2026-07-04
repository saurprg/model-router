from __future__ import annotations

from collections.abc import AsyncIterator

from app.schemas import ChatCompletionChunk

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


async def sse_stream(
    chunks: AsyncIterator[ChatCompletionChunk],
) -> AsyncIterator[str]:
    async for chunk in chunks:
        yield f"data: {chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import get_request_id
from app.orchestrator import FallbackOrchestrator, get_orchestrator
from app.schemas import ChatCompletionRequest
from app.streaming import SSE_HEADERS, sse_stream

router = APIRouter(prefix="/v1", tags=["chat"])

ROUTED_PROVIDER_HEADER = "X-Routed-Provider"


async def run_chat_completion(
    body: ChatCompletionRequest,
    orchestrator: FallbackOrchestrator,
    request_id: str,
) -> JSONResponse | StreamingResponse:
    if body.stream:
        stream = await orchestrator.execute_stream(body, request_id)
        return StreamingResponse(
            sse_stream(stream.chunks),
            media_type="text/event-stream",
            headers={
                **SSE_HEADERS,
                ROUTED_PROVIDER_HEADER: stream.routed_provider,
            },
        )

    result = await orchestrator.execute(body, request_id)
    return JSONResponse(
        content=result.response.model_dump(),
        headers={ROUTED_PROVIDER_HEADER: result.routed_provider},
    )


@router.post("/chat/completions", response_model=None)
async def chat_completions(
    body: ChatCompletionRequest,
    orchestrator: FallbackOrchestrator = Depends(get_orchestrator),
    request_id: str = Depends(get_request_id),
) -> JSONResponse | StreamingResponse:
    return await run_chat_completion(body, orchestrator, request_id)

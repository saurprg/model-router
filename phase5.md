# Phase 5 — Streaming Module (SSE Proxy)

> **Status:** Implemented. Adapter `stream()` from Phase 4 + client-facing SSE via `sse_stream()`.

Related: [`implementation_steps.md`](implementation_steps.md) · [`phase4.md`](phase4.md) · [`scope.md`](../scope.md) §5.D

---

## Goal

Convert typed `ChatCompletionChunk` objects into **OpenAI-compatible SSE** for the HTTP client.

```text
Adapter.stream()  →  AsyncIterator[ChatCompletionChunk]  →  sse_stream()  →  AsyncIterator[str]
                                                                    ↓
                                              StreamingResponse (Phase 5.2 / Phase 7)
```

**Separation of concerns:**

| Layer | Responsibility |
|---|---|
| `OpenAIAdapter.stream()` | Upstream HTTP + parse provider SSE → typed chunks |
| `streaming/proxy.py` | Format chunks → `data: {...}\n\n` + final `[DONE]` |
| Orchestrator (Phase 6) | Which adapter to call; fallback before first token |
| `api/v1/chat.py` (Phase 7) | `StreamingResponse` + headers |

Phase 5 does **not** implement fallback or the public `/v1/chat/completions` route — only the formatting pipeline and a debug hook to prove streaming works.

---

## Prerequisites (done)

- Phase 4: `OpenAIAdapter.stream()` in [`app/providers/openai_adapter.py`](app/providers/openai_adapter.py)
- `ChatCompletionChunk` / `StreamChoice` / `Delta` in [`app/schemas.py`](app/schemas.py)
- Shared `httpx.AsyncClient` on `app.state.http`
- Working non-stream path: `POST /debug/complete` with `"stream": false`

**Keys for manual testing:**

- Groq: `GROQ_API_KEY` → alias `fast/demo` (most reliable)
- DO: `DO_MODEL_ACCESS_KEY` → alias `do/llama`, `do/openai`, etc.

---

## What Phase 5 adds

### Step 5.1 — `app/streaming/proxy.py`

**Pattern:** Iterator / generator pipeline (thin, no business logic)

```python
async def sse_stream(
    chunks: AsyncIterator[ChatCompletionChunk],
) -> AsyncIterator[str]:
    async for chunk in chunks:
        yield f"data: {chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"
```

**Rules:**

- One SSE event per chunk; blank line between events (`\n\n`)
- Always terminate with `data: [DONE]\n\n` on successful completion
- Do **not** re-parse or reshape chunk JSON — adapters already normalize to OpenAI shape
- Do **not** catch adapter/orchestrator errors here (Phase 6 handles pre-first-token fallback; Phase 7 maps errors to HTTP)

**Optional helper (same file):**

```python
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable nginx buffering if proxied
}
```

Use these when returning `StreamingResponse` in Step 5.2.

---

### Step 5.2 — Wire debug streaming endpoint

Extend [`app/main.py`](app/main.py) so streaming can be tested **before** Phase 6 orchestrator.

**Option A (recommended):** Branch existing `/debug/complete`:

```python
if body.stream:
    adapter = get_adapter(target.provider, http, registry)
    chunks = adapter.stream(body, target)          # primary only, same as non-stream today
    return StreamingResponse(
        sse_stream(chunks),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
return response.model_dump()
```

**Option B:** Separate `POST /debug/stream` — clearer but duplicates routing logic.

For MVP, **Option A** keeps one debug surface; document that it still hits **primary target only** until Phase 6.

**Request body:** same as non-stream — use `"model"` (logical alias), not `logical_model`:

```json
{
  "model": "fast/demo",
  "messages": [{"role": "user", "content": "Count to 5"}],
  "stream": true
}
```

---

### Step 5.3 — `app/streaming/__init__.py`

Export public API:

```python
from app.streaming.proxy import SSE_HEADERS, sse_stream

__all__ = ["SSE_HEADERS", "sse_stream"]
```

---

### Step 5.4 — Unit tests (`tests/test_streaming_proxy.py`)

Test the proxy **in isolation** — no network, no adapters.

| Test | Assert |
|---|---|
| `test_sse_stream_formats_chunks` | Mock async generator of 2 chunks → output lines start with `data: `, valid JSON, ends with `data: [DONE]\n\n` |
| `test_sse_stream_empty_iterator` | Zero chunks still yields `[DONE]` |
| `test_chunk_json_matches_schema` | Serialized chunk includes `"object":"chat.completion.chunk"` |

**Optional integration test** (marked `@pytest.mark.integration` or skipped without keys):

- Call real Groq via adapter + `sse_stream`, collect lines, assert at least one content delta before `[DONE]`.

Adapter stream parsing is already covered implicitly by Phase 4; add `test_stream_success` in `test_openai_adapter.py` only if respx SSE mock is easy (nice-to-have, not blocking).

---

## Out of scope (Phase 6+)

| Concern | Owner |
|---|---|
| Fallback chain on stream failure | Phase 6 orchestrator |
| Mid-stream error → error chunk + `[DONE]` | Phase 6 / Phase 7 |
| `POST /v1/chat/completions` | Phase 7 |
| Auth / `X-Request-Id` headers | Phase 2 (deferred) |
| Anthropic SSE translation | Phase 4b |

**Streaming rule to remember for Phase 6:** fallback only **before first token**; after tokens are sent, fail gracefully — do not switch providers mid-answer.

---

## Files to create / touch

| File | Action |
|---|---|
| `app/streaming/proxy.py` | **Create** — `sse_stream`, `SSE_HEADERS` |
| `app/streaming/__init__.py` | **Create** — exports |
| `app/main.py` | **Edit** — `stream=true` branch on `/debug/complete` |
| `tests/test_streaming_proxy.py` | **Create** — unit tests |
| `implementation_steps.md` | Mark Phase 5 complete when done |

**Do not touch:** `orchestrator/`, `api/v1/`, adapter parsing logic (unless fixing a stream bug).

---

## Verify

### Unit tests

```bash
cd /workspaces/model-router && source .venv/bin/activate
pytest tests/test_streaming_proxy.py -q
```

### Manual — Groq (recommended)

```bash
# Start server if not running
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

curl -N http://127.0.0.1:8000/debug/complete \
  -H "Content-Type: application/json" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Count to 5 slowly"}],"stream":true}'
```

**Expected output:**

```text
data: {"id":"...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"1"},...}]}

data: {"id":"...","object":"chat.completion.chunk",...}

data: [DONE]
```

Use `curl -N` (no buffer) so tokens appear incrementally.

### Manual — DigitalOcean

```bash
curl -N http://127.0.0.1:8000/debug/complete \
  -H "Content-Type: application/json" \
  -d '{"model":"do/llama","messages":[{"role":"user","content":"Say hi"}],"stream":true}'
```

---

## Exit criteria

- [x] `sse_stream()` converts `ChatCompletionChunk` → valid OpenAI SSE lines
- [x] Stream always ends with `data: [DONE]\n\n`
- [x] `/debug/complete` with `"stream": true` returns `Content-Type: text/event-stream`
- [x] `pytest tests/test_streaming_proxy.py` passes
- [x] Live curl against `fast/demo` shows token-by-token output

---

## Estimated time

~20 minutes (matches implementation_steps.md).

---

## Next: Phase 7

[`app/api/v1/chat.py`](app/api/v1/chat.py) — public `POST /v1/chat/completions`. See [`phase6.md`](phase6.md) (orchestrator — done).

# Phase 7 — HTTP API Layer

> **Status:** Implemented. Public OpenAI-compatible routes delegate to orchestrator + SSE proxy.

Related: [`implementation_steps.md`](implementation_steps.md) · [`phase6.md`](phase6.md) · [`phase2.md`](phase2.md) (auth deferred)

---

## Goal

Expose the gateway as a standard OpenAI API surface. Handlers contain **zero routing logic** — all inference goes through [`FallbackOrchestrator`](app/orchestrator/fallback.py).

| Route | Method | Behavior |
|---|---|---|
| `/v1/chat/completions` | POST | Non-stream JSON or SSE stream via fallback chain |
| `/v1/models` | GET | List logical model aliases from `models.yaml` |

**Auth:** Unauthenticated for MVP (Phase 2 adds `Authorization: Bearer`).

---

## Files

| File | Role |
|---|---|
| [`app/api/deps.py`](app/api/deps.py) | `get_request_id()`, `get_registry()` |
| [`app/api/v1/chat.py`](app/api/v1/chat.py) | `run_chat_completion()` + POST handler |
| [`app/api/v1/models.py`](app/api/v1/models.py) | GET `/v1/models` |
| [`app/api/v1/__init__.py`](app/api/v1/__init__.py) | Composed v1 router |
| [`app/main.py`](app/main.py) | Mount v1 router; `/debug/complete` uses shared handler |
| [`tests/test_chat_api.py`](tests/test_chat_api.py) | TestClient + mocked orchestrator |

---

## Shared handler

Both `/v1/chat/completions` and `/debug/complete` call `run_chat_completion()`:

```python
if body.stream:
    return StreamingResponse(sse_stream(orchestrator.execute_stream(...)), ...)
return await orchestrator.execute(...)
```

---

## Verify

```bash
cd /workspaces/model-router && source .venv/bin/activate
pytest tests/test_chat_api.py tests/ -q
```

### Manual — non-stream

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Say hi"}],"stream":false}' | jq
```

### Manual — stream

```bash
curl -N http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Count to 5"}],"stream":true}'
```

### Manual — models list

```bash
curl -s http://127.0.0.1:8000/v1/models | jq
```

### Manual — fallback

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"smart/general","messages":[{"role":"user","content":"Say hi"}],"stream":false}' | jq '.model'
```

---

## Exit criteria

- [x] `POST /v1/chat/completions` — stream + non-stream
- [x] `GET /v1/models` — logical aliases
- [x] `/debug/complete` uses shared `run_chat_completion()`
- [x] `tests/test_chat_api.py` passes
- [x] Live curl against running server

---

## Out of scope

- Auth middleware → Phase 2
- `X-Request-Id` / `X-Routed-Provider` headers → Phase 2 / 9

---

## Next

**Phase 9** — structured logging, response headers, README + demo script. See [`phase8.md`](phase8.md) (health circuit — done).

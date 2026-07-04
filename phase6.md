# Phase 6 — Fallback Orchestrator

> **Status:** Implemented. Sequential fallback for non-stream and stream; stream locks target after first chunk.

Related: [`implementation_steps.md`](implementation_steps.md) · [`phase5.md`](phase5.md)

---

## Goal

Single entry point for inference: resolve logical model → try targets in order → retry on `RetryableError`, stop on `FatalError`.

| Method | Behavior |
|---|---|
| `execute(request, request_id)` | Non-stream: try each target until one succeeds |
| `execute_stream(request, request_id)` | Stream: fallback only **before** first chunk; no mid-answer switch |

**Patterns:** Chain of Responsibility + Facade

---

## Files

| File | Role |
|---|---|
| [`app/orchestrator/fallback.py`](app/orchestrator/fallback.py) | `FallbackOrchestrator` |
| [`app/orchestrator/__init__.py`](app/orchestrator/__init__.py) | Exports + `get_orchestrator()` for Phase 7 |
| [`app/main.py`](app/main.py) | `app.state.orchestrator`; `/debug/complete` delegates here |
| [`tests/test_fallback.py`](tests/test_fallback.py) | Mock-adapter unit tests |

---

## Error policy

| Error | Action |
|---|---|
| `RetryableError` (401, 403, 429, 5xx, missing key, timeout) | Log attempt, try next target |
| `FatalError` (400, unknown model) | Raise immediately — no fallback |
| All targets exhausted | `AllProvidersFailed` → HTTP 502 |

**Stream rule:** After any chunk is yielded, a `RetryableError` propagates — fallback is not attempted.

---

## Verify

```bash
cd /workspaces/model-router && source .venv/bin/activate
pytest tests/test_fallback.py -q
pytest tests/ -q
```

### Manual — fallback (unset or invalidate `GROQ_API_KEY`)

```bash
curl -s http://127.0.0.1:8000/debug/complete \
  -H "Content-Type: application/json" \
  -d '{"model":"smart/general","messages":[{"role":"user","content":"Say hi"}],"stream":false}' | jq
```

Expect upstream model `llama3.3-70b-instruct` (first DO fallback).

### Manual — stream through orchestrator

```bash
curl -N http://127.0.0.1:8000/debug/complete \
  -H "Content-Type: application/json" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Count to 3"}],"stream":true}'
```

---

## Exit criteria

- [x] `FallbackOrchestrator` implements `execute()` and `execute_stream()`
- [x] `/debug/complete` uses orchestrator for stream + non-stream
- [x] `tests/test_fallback.py` passes
- [ ] Manual fallback test with Groq key disabled

---

## Out of scope

- `POST /v1/chat/completions` → Phase 7
- Real request IDs → Phase 2 middleware
- Health-based skip → Phase 8
- SSE error chunks on mid-stream failure → Phase 7 polish

---

## Next: Phase 2 or Phase 8

Public API is live at `/v1/chat/completions`. See [`phase7.md`](phase7.md).

- **Phase 2** — auth + request-ID middleware (recommended before production)
- **Phase 8** — provider health circuit breaker

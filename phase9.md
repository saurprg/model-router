# Phase 9 — Observability + Polish

> **Status:** Implemented. Request tracing, structured logs, routing headers, README + demo script.

Related: [`implementation_steps.md`](implementation_steps.md) · [`phase8.md`](phase8.md) · [`phase2.md`](phase2.md) (auth still deferred)

---

## Goal

| Deliverable | Status |
|---|---|
| `X-Request-Id` on every response | Done via `RequestIdMiddleware` |
| JSON `inference_attempt` logs | Done in orchestrator |
| `X-Routed-Provider` on success | Done in `run_chat_completion()` |
| `README.md` + `scripts/demo.sh` | Done |

---

## Files

| File | Role |
|---|---|
| [`app/middleware/request_id.py`](app/middleware/request_id.py) | Request ID middleware |
| [`app/logging_config.py`](app/logging_config.py) | `log_event()` JSON helper |
| [`app/orchestrator/results.py`](app/orchestrator/results.py) | `CompletionResult`, `StreamResult` |
| [`app/orchestrator/fallback.py`](app/orchestrator/fallback.py) | Structured logs + result types |
| [`app/api/v1/chat.py`](app/api/v1/chat.py) | Response headers on success |
| [`tests/test_observability.py`](tests/test_observability.py) | Header + log tests |
| [`README.md`](README.md) | Project docs |
| [`scripts/demo.sh`](scripts/demo.sh) | End-to-end demo curls |

---

## Verify

```bash
cd /workspaces/model-router && source .venv/bin/activate
pytest tests/ -q

curl -i http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: my-trace-1" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Say hi"}],"stream":false}'

./scripts/demo.sh
```

---

## Exit criteria

- [x] `RequestIdMiddleware` + `X-Request-Id` on all responses
- [x] JSON `inference_attempt` logs with `latency_ms` + `outcome`
- [x] `X-Routed-Provider` on successful chat responses
- [x] `README.md` + `scripts/demo.sh`
- [x] Tests pass (36 total)

---

## Next

**Phase 2** — auth middleware, or **Phase 10** — optional test polish.

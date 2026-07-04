# Phase 8 — Provider Health / Circuit Breaker

> **Status:** Implemented. In-memory per-provider circuit breaker integrated into fallback orchestrator.

Related: [`implementation_steps.md`](implementation_steps.md) · [`phase7.md`](phase7.md)

---

## Goal

Skip upstream providers that are repeatedly failing. After **3 consecutive retryable failures**, the provider is bypassed for **60 seconds** without calling its adapter.

**Note:** `GET /health` is gateway liveness. This phase tracks **upstream provider** health (`groq`, `digitalocean`, etc.).

---

## Files

| File | Role |
|---|---|
| [`app/router/health.py`](app/router/health.py) | `ProviderHealth` — failure counter + cooldown |
| [`app/orchestrator/fallback.py`](app/orchestrator/fallback.py) | Skip unhealthy; `record_failure` / `record_success` |
| [`app/main.py`](app/main.py) | `app.state.provider_health` wired into orchestrator |
| [`tests/test_health.py`](tests/test_health.py) | Unit + orchestrator integration tests |

---

## Rules

| Event | Behavior |
|---|---|
| `record_failure()` | Increment consecutive failures; at threshold (3), open circuit for 60s |
| `record_success()` | Reset failures and clear cooldown |
| `is_healthy()` | False during cooldown; lazy recovery when cooldown expires |
| Unhealthy skip | Log `"skipping unhealthy provider"`; try next target (no HTTP call) |
| `FatalError` | Does not affect provider health |

---

## Verify

```bash
cd /workspaces/model-router && source .venv/bin/activate
pytest tests/test_health.py tests/ -q
```

### Manual — open circuit on Groq

**Why logs were missing:** Uvicorn only prints its own access logs by default. App loggers are now configured in [`app/logging_config.py`](app/logging_config.py) — restart uvicorn after pulling latest code. You should see lines like:

```text
WARNING app.orchestrator.fallback: skipping unhealthy provider provider=groq ...
```

**Inspect circuit state (no logs needed):**

```bash
curl -s http://127.0.0.1:8000/debug/health/providers | jq
```

After 3 Groq failures, expect `"groq": { "healthy": false, "consecutive_failures": 3, ... }`.

Temporarily invalidate `GROQ_API_KEY`, then:

```bash
for i in 1 2 3; do
  curl -s http://127.0.0.1:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"smart/general","messages":[{"role":"user","content":"hi"}],"stream":false}' | jq -r '.error.code // .model'
done

curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"smart/general","messages":[{"role":"user","content":"hi"}],"stream":false}' | jq '.model'
```

Fourth request should skip Groq quickly and fall back to DO (`llama3.3-70b-instruct` if DO key is valid). Check logs for `"skipping unhealthy provider"`.

---

## Exit criteria

- [x] `ProviderHealth` with threshold=3, recovery=60s
- [x] Orchestrator skips unhealthy providers before adapter calls
- [x] `record_failure` / `record_success` on retryable failure and success
- [x] `tests/test_health.py` passes; full suite green
- [ ] Manual circuit-breaker test with bad Groq key

---

## Out of scope

- Persistent health (Redis) — post-MVP
- Per-model health — post-MVP
- Structured logging polish — Phase 9
- Auth — Phase 2

---

## Next: Phase 2 or Phase 10

See [`phase9.md`](phase9.md) (observability — done).

- **Phase 2** — auth middleware (`Authorization: Bearer`)
- **Phase 10** — optional test polish

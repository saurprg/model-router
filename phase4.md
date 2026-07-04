# Phase 4 — Provider Adapter Layer

> **Status:** Implemented (Groq via OpenAI-compatible adapter). Anthropic adapter deferred.

Related: [`implementation_steps.md`](implementation_steps.md) · [`phase3.md`](phase3.md)

---

## Goal

Translate gateway requests to upstream LLM HTTP calls. Normalize responses to [`app/schemas.py`](app/schemas.py).

| Component | File |
|---|---|
| Protocol + error mapping | `app/providers/base.py` |
| OpenAI-compatible adapter (OpenAI + Groq) | `app/providers/openai_adapter.py` |
| Factory | `app/providers/__init__.py` |

---

## Prerequisites (done)

- Phase 1 + 3 complete
- `GROQ_API_KEY` in `.env` (gitignored)
- `config/models.yaml` — Groq primary for `smart/general` and `fast/demo`

---

## Verify

```bash
cd /workspaces/model-router && source .venv/bin/activate
pytest tests/test_openai_adapter.py tests/test_registry.py -q

curl -s http://127.0.0.1:8000/debug/complete \
  -H "Content-Type: application/json" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Say hi"}],"stream":false}'
```

DigitalOcean testing: see [`testing-do.md`](testing-do.md).

---

## Deferred

- Step 4.3 — `anthropic_adapter.py` (Phase 4b / before fallback demo)
- Phase 2 auth middleware

---

## Next: Phase 6

`app/orchestrator/fallback.py` — fallback chain for complete + stream. See [`phase5.md`](phase5.md) (streaming proxy — done).

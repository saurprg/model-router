# Model Router

OpenAI-compatible HTTP gateway that routes logical model aliases to upstream LLM providers with sequential fallback, streaming, and per-provider circuit breaking.

## Quick start

```bash
cd model-router
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your API keys
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Environment variables

| Variable | Purpose |
|---|---|
| `GATEWAY_API_KEY` | Client auth for the gateway (Phase 2 — not enforced yet) |
| `GROQ_API_KEY` | Groq upstream (`fast/demo`, `smart/general` primary) |
| `DO_MODEL_ACCESS_KEY` | DigitalOcean Gradient inference gateway |
| `OPENAI_API_KEY` | Optional native OpenAI (if configured in routes) |
| `ANTHROPIC_API_KEY` | Optional native Anthropic (if configured in routes) |

## Logical model aliases

| Alias | Primary | Fallbacks |
|---|---|---|
| `fast/demo` | Groq | — |
| `smart/general` | Groq | DO Llama → DO OpenAI → DO Anthropic |
| `do/llama` | DO Llama 3.3 70B | — |
| `do/openai` | DO OpenAI nano | — |
| `do/anthropic` | DO Claude Haiku | — |

Configure routes in [`config/models.yaml`](config/models.yaml).

## API

| Endpoint | Description |
|---|---|
| `GET /health` | Gateway liveness |
| `GET /v1/models` | List logical model aliases |
| `POST /v1/chat/completions` | OpenAI-compatible chat (stream + non-stream) |
| `GET /debug/routes/{alias}` | Show resolved fallback chain |
| `GET /debug/health/providers` | Per-provider circuit breaker state |

### Example — non-stream

```bash
curl -i http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: my-trace-1" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Say hi"}],"stream":false}'
```

Response headers include `X-Request-Id` and `X-Routed-Provider` on success.

### Example — stream

```bash
curl -N http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Count to 5"}],"stream":true}'
```

## Demo script

```bash
chmod +x scripts/demo.sh
./scripts/demo.sh
```

## Tests

```bash
pytest tests/ -q
```

## Architecture docs

- [`implementation_steps.md`](implementation_steps.md) — build checklist
- [`phase9.md`](phase9.md) — observability (request ID, structured logs, headers)

Auth middleware is planned in [`phase2.md`](phase2.md) (not enabled yet).

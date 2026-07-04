# Testing DigitalOcean Gradient Inference

DigitalOcean uses a **single OpenAI-compatible gateway** — not native `api.openai.com` / `api.anthropic.com`.

| Setting | Value |
|---|---|
| Base URL | `https://inference.do-ai.run/v1` |
| Env var | `DO_MODEL_ACCESS_KEY` |
| Adapter | `OpenAIAdapter` via `digitalocean` provider |

Model slugs use DO naming (e.g. `openai-gpt-5-nano`, `anthropic-claude-haiku-4.5`). Catalog listing does not guarantee your tier can invoke a model — start with nano/haiku/flash tiers.

```bash
source .venv/bin/activate
export DO_MODEL_ACCESS_KEY="your-key-from-.env"

curl -s https://inference.do-ai.run/v1/models \
  -H "Authorization: Bearer $DO_MODEL_ACCESS_KEY" \
  | python -m json.tool
```

Update slugs in `config/models.yaml` if needed.

---

## 1. Direct DO test (bypass gateway)

```bash
curl -s https://inference.do-ai.run/v1/chat/completions \
  -H "Authorization: Bearer $DO_MODEL_ACCESS_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai-gpt-5-nano",
    "messages": [{"role": "user", "content": "Say hi"}],
    "stream": false
  }'
```

Anthropic-branded model on same endpoint:

```bash
curl -s https://inference.do-ai.run/v1/chat/completions \
  -H "Authorization: Bearer $DO_MODEL_ACCESS_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic-claude-haiku-4.5",
    "messages": [{"role": "user", "content": "Say hi"}],
    "stream": false
  }'
```

---

## 2. Gateway routing test

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

curl -s http://127.0.0.1:8000/debug/routes/do/openai | python -m json.tool
curl -s http://127.0.0.1:8000/debug/routes/smart/general | python -m json.tool
```

---

## 3. Gateway completion test

```bash
curl -s http://127.0.0.1:8000/debug/complete \
  -H "Content-Type: application/json" \
  -d '{"model":"do/openai","messages":[{"role":"user","content":"Say hi"}],"stream":false}'

curl -s http://127.0.0.1:8000/debug/complete \
  -H "Content-Type: application/json" \
  -d '{"model":"do/anthropic","messages":[{"role":"user","content":"Say hi"}],"stream":false}'
```

---

## Logical model aliases

| Alias | Primary | Fallbacks |
|---|---|---|
| `do/openai` | DO → `openai-gpt-5-nano` | — |
| `do/anthropic` | DO → `anthropic-claude-haiku-4.5` | — |
| `smart/general` | Groq | DO OpenAI → DO Anthropic |
| `fast/demo` | Groq only | — |

---

## Notes

- Do **not** put DO keys in `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` unless using native provider URLs.
- Keep secrets in `.env` only — not in `.env.example`.
- `/debug/complete` hits **primary target only**; full fallback chain comes in Phase 6.

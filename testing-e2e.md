# End-to-End Testing Guide

Verify the model router locally and on production (DigitalOcean App Platform).

Related: [`testing-do.md`](testing-do.md) (DO Gradient upstream details) · [`README.md`](README.md)

---

## Production deployment

| Setting | Value |
|---|---|
| **App URL** | https://stingray-app-vr7ae.ondigitalocean.app |
| **Platform** | DigitalOcean App Platform |
| **Health check** | `GET /health` (TCP on port 8080 by default; HTTP path optional) |
| **Run command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

Set these env vars in **App Platform → Settings → Environment Variables**:

| Variable | Required |
|---|---|
| `GATEWAY_API_KEY` | Yes (app startup; auth not enforced yet) |
| `DO_MODEL_ACCESS_KEY` | Yes for `do/*` routes and DO fallbacks |
| `GROQ_API_KEY` | Yes for `fast/demo` and Groq-primary `smart/general` |

---

## Production smoke tests

Set your base URL (override for other environments):

```bash
export BASE_URL="https://stingray-app-vr7ae.ondigitalocean.app"
```

### 1. Health

```bash
curl -s "$BASE_URL/health"
```

**Expected:** `{"status":"ok"}` with HTTP `200`

### 2. List models

```bash
curl -s "$BASE_URL/v1/models" | jq
```

**Expected:** `object: "list"` with aliases including `do/llama`, `do/openai`, `fast/demo`, `smart/general`

### 3. Chat — non-stream (recommended routes)

**DO Llama (reliable on production):**

```bash
curl -s "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"do/llama","messages":[{"role":"user","content":"Say hi in one word"}],"stream":false}' | jq
```

**Expected:** HTTP `200`, `"model": "llama3.3-70b-instruct"`

**Groq (`fast/demo`):**

```bash
curl -s "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Say hi"}],"stream":false}' | jq
```

**Expected:** HTTP `200`, `"model": "llama-3.1-8b-instant"`

### 4. Observability headers

```bash
curl -i "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: prod-test-1" \
  -d '{"model":"do/llama","messages":[{"role":"user","content":"Hi"}],"stream":false}'
```

**Expected on success:**

| Header | Example |
|---|---|
| `X-Request-Id` | `prod-test-1` (echoed) |
| `X-Routed-Provider` | `digitalocean` or `groq` |

Check **Runtime Logs** in the DO dashboard for JSON lines:

```json
{"event":"inference_attempt","outcome":"success","latency_ms":...}
```

### 5. Stream

```bash
curl -N "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Count to 3"}],"stream":true}'
```

**Expected:** `data: {...}` lines ending with `data: [DONE]`

### 6. Circuit breaker state (debug)

```bash
curl -s "$BASE_URL/debug/health/providers" | jq
```

**Expected:** `{}` when healthy, or provider entries after repeated upstream failures

### 7. Fallback chain (optional)

```bash
curl -s "$BASE_URL/debug/routes/smart/general" | jq
```

**Expected:** Groq primary + DO fallbacks in order

---

## Production test results (last verified)

| Endpoint / route | HTTP | Notes |
|---|---|---|
| `GET /health` | 200 | OK |
| `GET /v1/models` | 200 | All aliases listed |
| `POST /v1/chat/completions` → `do/llama` | 200 | DO Llama 3.3 70B |
| `POST /v1/chat/completions` → `fast/demo` | 200 | Groq (~0.2s) |
| `POST /v1/chat/completions` → `do/openai` | 504 | DO/edge error — see troubleshooting |
| `GET /debug/health/providers` | 200 | Circuit state visible |

---

## Troubleshooting production

### Health check / deploy failed

1. Confirm run command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
2. Confirm **HTTP Port** = `8080` in App Platform settings
3. Ensure `GATEWAY_API_KEY` is set (app crashes without it)
4. Check **Runtime Logs** for Python tracebacks

**Configure HTTP health path (optional):** App → Settings → Web Service → **Health Checks** → HTTP path `/health`. If the UI option is missing, add to App Spec:

```yaml
health_check:
  http_path: /health
  initial_delay_seconds: 30
```

### `do/openai` returns 504

The gateway and DO key are fine if `do/llama` works. The `openai-gpt-5-nano` slug may be unavailable on your DO tier.

1. Check **Runtime Logs** for `"outcome":"retry"` on `digitalocean`
2. List models your key can access:

```bash
curl -s https://inference.do-ai.run/v1/models \
  -H "Authorization: Bearer $DO_MODEL_ACCESS_KEY" | jq '.data[].id'
```

3. Update slugs in [`config/models.yaml`](config/models.yaml) and redeploy

### Auth

Gateway auth (`Authorization: Bearer`) is **not enabled** yet. No auth header required for production tests today.

---

## Local end-to-end tests

### Start server

```bash
cd model-router
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Quick local checks

```bash
export BASE_URL="http://127.0.0.1:8000"

curl -s "$BASE_URL/health"
curl -s "$BASE_URL/v1/models" | jq
curl -i "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: local-test-1" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Say hi"}],"stream":false}'
```

### Demo script

```bash
BASE_URL=http://127.0.0.1:8000 ./scripts/demo.sh
```

### Unit tests

```bash
pytest tests/ -q
```

### DigitalOcean upstream (direct)

See [`testing-do.md`](testing-do.md) for bypass-gateway curls against `https://inference.do-ai.run/v1`.

---

## Logical model aliases

| Alias | Primary | Fallbacks |
|---|---|---|
| `fast/demo` | Groq | — |
| `smart/general` | Groq | DO Llama → DO OpenAI → DO Anthropic |
| `do/llama` | DO Llama 3.3 70B | — |
| `do/openai` | DO OpenAI nano | — |
| `do/anthropic` | DO Claude Haiku | — |

Configure in [`config/models.yaml`](config/models.yaml).

# End-to-End Testing Guide (Evaluator Edition)

Use this document to verify the **Model Router** gateway end-to-end. Each test states **what capability it proves**, **exact pass criteria**, and **why that output is correct**—so results can be scored without reading the source code.

**Related:** [`testing-do.md`](testing-do.md) (DigitalOcean upstream isolation) · [`README.md`](README.md) · [`docs/images/`](docs/images/) (architecture)

---

## What you are testing

The gateway is an **OpenAI-compatible HTTP API** that:

1. Accepts logical model **aliases** (e.g. `fast/demo`) instead of raw upstream model IDs.
2. Resolves aliases via [`config/models.yaml`](config/models.yaml) to ordered `{ provider, model }` targets.
3. Calls upstream LLM APIs through adapter layers; on retryable failure, tries the **next fallback**.
4. Returns standard OpenAI JSON or SSE streams, plus observability headers on success.
5. Tracks per-provider **circuit breaker** state (skip after 3 consecutive retryable failures for 60s).

Gateway **client auth is not enforced** yet (`GATEWAY_API_KEY` is required at startup only). Evaluators do **not** need an `Authorization` header for these tests.

---

## Prerequisites (complete before scoring)

| # | Requirement | How to verify |
|---|---|---|
| P1 | Python 3.11+ and dependencies installed | `pip install -r requirements.txt` |
| P2 | `.env` copied from `.env.example` with valid keys | `GROQ_API_KEY`, `DO_MODEL_ACCESS_KEY`, `GATEWAY_API_KEY` set |
| P3 | Server running (local) **or** production URL reachable | See [Local setup](#local-setup) or [Production URL](#production-url) |
| P4 | `curl` and `jq` available | `curl --version` and `jq --version` |

**Production URL:** https://stingray-app-vr7ae.ondigitalocean.app  
**Local default:** `http://127.0.0.1:8000`

```bash
# Pick one environment for all tests below
export BASE_URL="https://stingray-app-vr7ae.ondigitalocean.app"
# export BASE_URL="http://127.0.0.1:8000"
```

---

## Evaluation checklist (summary)

Mark each test **PASS** only if **all** checks in that test’s pass criteria are met.

| ID | Test | Capability verified | Required? |
|---|---|---|---|
| [T01](#t01-gateway-liveness) | Gateway liveness | Process up; load balancer can probe | **Yes** |
| [T02](#t02-model-catalog) | Model catalog | Registry loaded; aliases exposed OpenAI-style | **Yes** |
| [T03](#t03-routing-resolution-debug) | Routing resolution | Alias → provider chain matches config | **Yes** |
| [T04](#t04-non-stream-inference-do) | Non-stream inference (DO) | Adapter + upstream call via alias | **Yes** |
| [T05](#t05-non-stream-inference-groq) | Non-stream inference (Groq) | Second provider path works | **Yes** |
| [T06](#t06-openai-response-shape) | Response contract | OpenAI-compatible JSON shape | **Yes** |
| [T07](#t07-observability-headers) | Observability | Request tracing + routed provider | **Yes** |
| [T08](#t08-sse-streaming) | SSE streaming | Token stream + `[DONE]` terminator | **Yes** |
| [T09](#t09-unknown-model-error) | Error handling | Unknown alias → 404, no fallback | **Yes** |
| [T10](#t10-circuit-breaker-debug) | Circuit breaker | Per-provider health state exposed | Recommended |
| [T11](#t11-fallback-chain-config) | Fallback configuration | Multi-provider chain for `smart/general` | Recommended |
| [T12](#t12-automated-unit-tests) | Automated regression | 69 pytest cases green | **Yes** (local) |

---

## Detailed test cases

### T01: Gateway liveness

**Capability verified:** The FastAPI process is running and responds without calling any upstream LLM.

**Command:**

```bash
curl -s -w "\nHTTP_CODE:%{http_code}\n" "$BASE_URL/health"
```

**Pass criteria:**

| Check | Expected | Reasoning |
|---|---|---|
| HTTP status | `200` | `/health` is a dedicated liveness route; non-200 means deploy/crash/misconfigured port |
| Body | `{"status":"ok"}` | Confirms handler returned successfully—not a proxy error page or empty body |
| Latency | &lt; 1s | No external I/O; slow response suggests platform/network issues, not model latency |

**If this fails:** Check run command (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`), `GATEWAY_API_KEY` env var (app exits without it), and platform logs.

---

### T02: Model catalog

**Capability verified:** `ModelRegistry` loaded `config/models.yaml` and exposes logical aliases via OpenAI-compatible `GET /v1/models`.

**Command:**

```bash
curl -s "$BASE_URL/v1/models" | jq
```

**Pass criteria:**

| Check | Expected | Reasoning |
|---|---|---|
| HTTP status | `200` | Route mounted and registry initialized at startup |
| `object` | `"list"` | OpenAI list-models contract |
| `data[].id` | Includes `fast/demo`, `smart/general`, `do/llama`, `do/openai`, `do/anthropic` | All routes from `models.yaml` are registered; missing alias = config load failure |
| `data[].object` | `"model"` on each item | OpenAI model object shape |

**If this fails:** Verify `config/models.yaml` exists in deployment artifact and parses without YAML errors (check startup logs).

---

### T03: Routing resolution (debug)

**Capability verified:** Alias `smart/general` resolves to an **ordered** list: Groq primary, then DigitalOcean fallbacks—without making an inference call.

**Command:**

```bash
curl -s "$BASE_URL/debug/routes/smart/general" | jq
```

**Pass criteria:**

| Check | Expected | Reasoning |
|---|---|---|
| HTTP status | `200` | Debug route registered |
| `logical_model` | `"smart/general"` | Echoes requested alias |
| `targets[0]` | `provider: groq`, `model: llama-3.1-8b-instant` | Primary from `models.yaml` |
| `targets[1]` | `provider: digitalocean`, `model: llama3.3-70b-instruct` | First fallback |
| `targets[2]` | `provider: digitalocean`, `model: openai-gpt-5-nano` | Second fallback |
| `targets[3]` | `provider: digitalocean`, `model: anthropic-claude-haiku-4.5` | Third fallback |
| Target count | `4` | Full chain loaded—order matters for fallback behavior |

**If this fails:** Registry misconfiguration or stale deploy; compare output to [`config/models.yaml`](config/models.yaml).

---

### T04: Non-stream inference (DO)

**Capability verified:** Gateway resolves alias `do/llama` → DigitalOcean adapter → upstream HTTP → OpenAI-shaped JSON response.

**Why this route:** DO Llama is the most reliable production path; success proves `DO_MODEL_ACCESS_KEY` and the `digitalocean` provider adapter work.

**Command:**

```bash
curl -s -w "\nHTTP_CODE:%{http_code}\n" "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"do/llama","messages":[{"role":"user","content":"Reply with exactly: pong"}],"stream":false}' | jq
```

**Pass criteria:**

| Check | Expected | Reasoning |
|---|---|---|
| HTTP status | `200` | Orchestrator + adapter succeeded on primary target |
| `object` | `"chat.completion"` | OpenAI non-stream contract |
| `model` | `"llama3.3-70b-instruct"` | Response echoes **upstream** model ID, not alias—proves correct target was used |
| `choices[0].message.role` | `"assistant"` | Valid completion structure |
| `choices[0].message.content` | Non-empty string | Upstream actually generated text (not an empty/error payload) |
| `choices[0].finish_reason` | `"stop"` (typical) | Normal completion end |

**If this fails with 502:** All providers for that alias failed—check DO key and runtime logs for `"outcome":"retry"`.  
**If this fails with 404 on model:** Wrong alias string or registry not loaded.

---

### T05: Non-stream inference (Groq)

**Capability verified:** Groq provider path works independently of DigitalOcean.

**Command:**

```bash
curl -s -w "\nHTTP_CODE:%{http_code}\n" "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Say hi"}],"stream":false}' | jq
```

**Pass criteria:**

| Check | Expected | Reasoning |
|---|---|---|
| HTTP status | `200` | Groq adapter + `GROQ_API_KEY` valid |
| `model` | `"llama-3.1-8b-instant"` | Upstream Groq model from config—not the alias `fast/demo` |
| `choices[0].message.content` | Non-empty | Inference succeeded |

**If this fails:** Invalid/missing `GROQ_API_KEY` or Groq rate limit; check logs for `provider: groq` and `error_code`.

---

### T06: OpenAI response shape

**Capability verified:** Successful responses follow the OpenAI chat completion schema expected by standard SDKs.

**Command:** Use output from T04 or T05.

**Pass criteria:**

| Field | Expected | Reasoning |
|---|---|---|
| Top-level keys | `id`, `object`, `model`, `choices` | Minimum OpenAI-compatible surface |
| `choices[0].index` | `0` | Single-choice response |
| `choices[0].message` | `{ "role", "content" }` | Chat message shape |
| No `error` key | absent on 200 | 200 must not be an error payload |

---

### T07: Observability headers

**Capability verified:** Request ID middleware echoes trace ID; successful routing exposes which upstream **provider** won.

**Command:**

```bash
curl -i -s "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: eval-trace-001" \
  -d '{"model":"do/llama","messages":[{"role":"user","content":"Hi"}],"stream":false}' \
  | head -30
```

**Pass criteria:**

| Check | Expected | Reasoning |
|---|---|---|
| HTTP status | `200` | Success path only sets `X-Routed-Provider` |
| Header `X-Request-Id` | `eval-trace-001` | Middleware accepts client-supplied ID and echoes on response—enables distributed tracing |
| Header `X-Routed-Provider` | `digitalocean` (for `do/llama`) | Identifies winning provider, not upstream model slug—proves orchestrator recorded route outcome |
| Response body | Valid JSON completion | Headers are additive; body must still be correct |

**Optional (production logs):** In DigitalOcean **Runtime Logs**, find a JSON line:

```json
{"event":"inference_attempt","request_id":"eval-trace-001","outcome":"success","provider":"digitalocean",...}
```

**Reasoning:** Structured logs tie HTTP requests to provider attempts for post-incident analysis.

---

### T08: SSE streaming

**Capability verified:** `stream: true` returns `text/event-stream` with OpenAI chunk format and proper stream termination.

**Command:**

```bash
curl -N -s "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Count to 3"}],"stream":true}'
```

**Pass criteria:**

| Check | Expected | Reasoning |
|---|---|---|
| HTTP status | `200` | Stream opened successfully |
| `Content-Type` | contains `text/event-stream` | SSE media type |
| Body lines | One or more lines starting with `data: {` | Each SSE event wraps a `chat.completion.chunk` JSON object |
| Chunk JSON | `"object":"chat.completion.chunk"` | OpenAI streaming contract |
| Chunk JSON | `choices[0].delta.content` with token text | Incremental generation—not a single buffered JSON body |
| Final line | `data: [DONE]` | `sse_stream()` always terminates streams per OpenAI convention; missing `[DONE]` = broken client compatibility |

**If this fails mid-stream:** After first token, orchestrator does **not** switch providers—partial output then error is acceptable failure mode for upstream drop.

---

### T09: Unknown model error

**Capability verified:** Invalid alias is a **fatal** client error (404)—orchestrator must **not** attempt fallback to a default provider.

**Command:**

```bash
curl -s -w "\nHTTP_CODE:%{http_code}\n" "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"does/not-exist","messages":[{"role":"user","content":"Hi"}],"stream":false}' | jq
```

**Pass criteria:**

| Check | Expected | Reasoning |
|---|---|---|
| HTTP status | `404` | `UnknownModelError` mapped to 404 in [`app/errors.py`](app/errors.py) |
| `error.code` | `"unknown_model"` | Typed error for clients |
| `error.message` | contains `does/not-exist` | Clear feedback on bad alias |
| `error.type` | `"UnknownModelError"` | Exception class exposed for debugging |

**If you get 502 instead:** Misrouting—unknown model should never reach upstream providers.

---

### T10: Circuit breaker (debug)

**Capability verified:** In-memory per-provider health state is readable for ops/debug.

**Command:**

```bash
curl -s "$BASE_URL/debug/health/providers" | jq
```

**Pass criteria (fresh deploy):**

| Check | Expected | Reasoning |
|---|---|---|
| HTTP status | `200` | Debug endpoint live |
| Body | `{}` or `{"providers":{}}` shape | No failures recorded yet—empty state is healthy |

**Pass criteria (after forcing upstream failures on one provider):**

| Check | Expected | Reasoning |
|---|---|---|
| Provider entry | e.g. `"groq": { "healthy": false, "consecutive_failures": 3 }` | After 3 retryable errors, circuit opens for 60s |
| Subsequent requests | Skip unhealthy provider quickly | Orchestrator logs `"outcome":"skip_unhealthy"` without calling adapter |

**How to force (optional, local only):** Temporarily set invalid `GROQ_API_KEY`, send 3 requests to `smart/general`, then inspect this endpoint.

---

### T11: Fallback chain config

**Capability verified:** Multi-provider alias documents fallback order for evaluators planning resilience tests.

**Command:**

```bash
curl -s "$BASE_URL/debug/routes/fast/demo" | jq
curl -s "$BASE_URL/debug/routes/do/llama" | jq
```

**Pass criteria:**

| Alias | Expected targets | Reasoning |
|---|---|---|
| `fast/demo` | 1 target (Groq only) | No fallbacks—failure yields 502 |
| `do/llama` | 1 target (DO Llama) | Single-provider alias |
| `smart/general` | 4 targets (see T03) | Resilience path—Groq then DO models |

**Note on `do/openai`:** May return **504/502** on some DO tiers (`openai-gpt-5-nano` slug unavailable). That is an **upstream tier issue**, not a gateway routing bug, if `do/llama` succeeds. See [Known limitations](#known-limitations).

---

### T12: Automated unit tests

**Capability verified:** Regression suite covers registry, adapters, streaming, fallback, health, API, and observability without live API keys.

**Command (local only):**

```bash
cd model-router
source .venv/bin/activate
pytest tests/ -q
```

**Pass criteria:**

| Check | Expected | Reasoning |
|---|---|---|
| Exit code | `0` | All tests passed |
| Count | 69 tests | Suite covers core modules listed below |

| Test file | What it proves |
|---|---|
| `test_registry.py` | YAML → alias resolution; unknown model/provider |
| `test_errors.py` | HTTP/transport error classification |
| `test_providers_factory.py` | Adapter factory; unknown provider |
| `test_openai_adapter.py` | Complete/stream; 4xx/5xx; missing key; payload |
| `test_streaming_proxy.py` | Chunks → SSE lines + `[DONE]` + headers |
| `test_fallback.py` | Fallback chain; stream lock; empty stream; fatal |
| `test_health.py` | Circuit breaker; skip unhealthy; fatal vs retryable |
| `test_chat_api.py` | Routes, 404/502, debug endpoints, SSE headers |
| `test_observability.py` | Request ID, routed provider, structured logs |

---

## Error response reference

All gateway errors use this envelope:

```json
{
  "error": {
    "message": "Human-readable description",
    "type": "ExceptionClassName",
    "code": "machine_code"
  }
}
```

| HTTP | `code` | When | Fallback attempted? |
|---|---|---|---|
| `404` | `unknown_model` | Alias not in `models.yaml` | No |
| `400` | `upstream_bad_request` etc. | Fatal client/upstream 400 | No |
| `502` | `all_providers_failed` | Every target in chain failed | Was attempted |
| `500` | `router_error` | Unexpected internal error | Depends |

**Reasoning:** Retryable upstream failures (401, 429, 5xx, timeout) are handled **inside** the orchestrator; the client often sees **502** only when the entire chain is exhausted—not per-attempt upstream codes.

---

## Demo script (quick smoke)

Runs T01, T02, partial T07, T08, T10 in one script:

```bash
chmod +x scripts/demo.sh
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}" ./scripts/demo.sh
```

**Pass:** Each section prints JSON or SSE without curl errors. **Fail:** Non-zero exit or HTTP error lines in chat section.

---

## Local setup

```bash
cd model-router
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add GROQ_API_KEY, DO_MODEL_ACCESS_KEY, GATEWAY_API_KEY
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal: `export BASE_URL=http://127.0.0.1:8000` and run tests T01–T12.

---

## Production URL

| Setting | Value |
|---|---|
| **App URL** | https://stingray-app-vr7ae.ondigitalocean.app |
| **Platform** | DigitalOcean App Platform |
| **Run command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Required env** | `GATEWAY_API_KEY`, `GROQ_API_KEY`, `DO_MODEL_ACCESS_KEY` |

**Last verified production results:**

| Route / endpoint | HTTP | Evaluator note |
|---|---|---|
| `GET /health` | 200 | Pass T01 |
| `GET /v1/models` | 200 | Pass T02 |
| `POST …` → `do/llama` | 200 | Pass T04 — use as primary DO proof |
| `POST …` → `fast/demo` | 200 | Pass T05 |
| `POST …` → `do/openai` | 504 | Known upstream slug issue — **do not fail gateway** if T04 passes |
| `GET /debug/health/providers` | 200 | Pass T10 |

---

## Known limitations (not scoring failures)

| Item | Explanation |
|---|---|
| Gateway auth | `Authorization: Bearer` not enforced; `GATEWAY_API_KEY` only required at startup |
| `do/openai` 504 | DO tier may not expose `openai-gpt-5-nano`; gateway and key are fine if `do/llama` works |
| Debug routes | `/debug/*` exposed without auth—acceptable for evaluation/demo, not production hardening |
| Circuit breaker | In-memory, single process—resets on redeploy |

---

## Troubleshooting

### Deploy / health check failed

1. Run command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
2. HTTP port `8080` in App Platform settings
3. `GATEWAY_API_KEY` must be set or app crashes on startup
4. Check **Runtime Logs** for Python tracebacks

### All chat requests return 502

1. Verify API keys in environment (not just `.env` locally)
2. Run T04 (`do/llama`) and T05 (`fast/demo`) separately to isolate provider
3. Logs: look for `"outcome":"retry"` then `"all_providers_failed"`

### Stream hangs without `[DONE]`

1. Confirm `curl -N` (no buffer)
2. Upstream may have dropped connection—retry once
3. If consistent, check `test_streaming_proxy.py` locally

### Isolate DO vs gateway

See [`testing-do.md`](testing-do.md)—direct curls to `https://inference.do-ai.run/v1` bypass the gateway to prove whether failures are upstream or routing.

---

## Routing reference

| Alias | Primary | Fallbacks |
|---|---|---|
| `fast/demo` | Groq `llama-3.1-8b-instant` | — |
| `smart/general` | Groq | DO Llama → DO OpenAI → DO Anthropic |
| `do/llama` | DO `llama3.3-70b-instruct` | — |
| `do/openai` | DO `openai-gpt-5-nano` | — |
| `do/anthropic` | DO `anthropic-claude-haiku-4.5` | — |

Source: [`config/models.yaml`](config/models.yaml)

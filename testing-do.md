# DigitalOcean Gradient Testing (Evaluator Edition)

Use this document to **isolate DigitalOcean (DO) upstream behavior** from gateway routing. When a gateway test fails, these steps show whether the problem is the **DO API/key/tier** or the **model router**.

**Related:** [`testing-e2e.md`](testing-e2e.md) (full gateway evaluation) · [`config/models.yaml`](config/models.yaml)

---

## Architecture context

DigitalOcean Gradient exposes a **single OpenAI-compatible endpoint** for all model brands:

| Setting | Value |
|---|---|
| Base URL | `https://inference.do-ai.run/v1` |
| Env var | `DO_MODEL_ACCESS_KEY` |
| Gateway provider name | `digitalocean` |
| Gateway adapter | `OpenAIAdapter` (same as Groq/OpenAI-compatible APIs) |

**Reasoning:** DO is not native `api.openai.com` or `api.anthropic.com`. Model IDs use DO slugs (e.g. `llama3.3-70b-instruct`, `openai-gpt-5-nano`). The gateway maps aliases like `do/llama` → `{ provider: digitalocean, model: llama3.3-70b-instruct }`.

---

## Prerequisites

```bash
source .venv/bin/activate
export DO_MODEL_ACCESS_KEY="your-key-from-.env"   # never commit real keys
```

| # | Requirement | Reasoning |
|---|---|---|
| P1 | Valid `DO_MODEL_ACCESS_KEY` | Without it, all DO calls return 401—indistinguishable from gateway misconfig |
| P2 | Network access to `inference.do-ai.run` | Corporate firewalls may block; direct test proves connectivity |

---

## Evaluation checklist

| ID | Test | Proves | Pass if |
|---|---|---|---|
| [D01](#d01-list-upstream-models) | List upstream models | Key is valid; catalog reachable | HTTP 200 + non-empty `data` |
| [D02](#d02-direct-do-llama) | Direct DO Llama call | Slug works on your tier | HTTP 200 + assistant content |
| [D03](#d03-direct-do-openai-slug) | Direct DO OpenAI slug | Tier access to nano model | 200 **or** documented tier limitation |
| [D04](#d04-gateway-route-resolution) | Gateway route debug | Alias maps to correct DO slug | Targets match `models.yaml` |
| [D05](#d05-gateway-do-alias) | Gateway `do/llama` | End-to-end DO path through router | HTTP 200 + upstream model in response |

**Scoring rule:** If **D02 passes** but gateway `do/llama` fails → gateway bug. If **D02 fails** → fix DO key/tier before scoring gateway DO tests.

---

## D01: List upstream models

**Capability verified:** API key is accepted and DO returns a model catalog.

**Command:**

```bash
curl -s -w "\nHTTP_CODE:%{http_code}\n" \
  https://inference.do-ai.run/v1/models \
  -H "Authorization: Bearer $DO_MODEL_ACCESS_KEY" | jq
```

**Pass criteria:**

| Check | Expected | Reasoning |
|---|---|---|
| HTTP status | `200` | Key valid; not expired or revoked |
| `data` | Array with ≥1 entry | Account has model access |
| Slugs | Ideally includes models you route to (e.g. `llama3.3-70b-instruct`) | Listing a slug does not guarantee invoke access on all tiers—D02 confirms invoke |

**If 401:** Wrong key, typo, or key not activated for Gradient inference.

---

## D02: Direct DO Llama call

**Capability verified:** Your tier can **invoke** Llama 3.3 70B—not just list it.

**Command:**

```bash
curl -s -w "\nHTTP_CODE:%{http_code}\n" \
  https://inference.do-ai.run/v1/chat/completions \
  -H "Authorization: Bearer $DO_MODEL_ACCESS_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.3-70b-instruct",
    "messages": [{"role": "user", "content": "Reply with exactly: pong"}],
    "stream": false
  }' | jq
```

**Pass criteria:**

| Check | Expected | Reasoning |
|---|---|---|
| HTTP status | `200` | Upstream inference succeeded |
| `model` | `"llama3.3-70b-instruct"` | Echoes requested slug |
| `choices[0].message.content` | Non-empty (ideally contains `pong`) | Model generated output—proves invoke, not just auth |

**Gateway mapping:** Alias `do/llama` uses this exact slug. **D02 pass + gateway `do/llama` fail** → investigate gateway adapter, env var name (`DO_MODEL_ACCESS_KEY` in deployment), or orchestrator—not DO tier.

---

## D03: Direct DO OpenAI slug

**Capability verified:** Whether `openai-gpt-5-nano` is invokable on your DO account.

**Command:**

```bash
curl -s -w "\nHTTP_CODE:%{http_code}\n" \
  https://inference.do-ai.run/v1/chat/completions \
  -H "Authorization: Bearer $DO_MODEL_ACCESS_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai-gpt-5-nano",
    "messages": [{"role": "user", "content": "Say hi"}],
    "stream": false
  }' | jq
```

**Pass criteria:**

| Outcome | HTTP | Evaluator interpretation |
|---|---|---|
| **Pass (tier OK)** | `200` + content | Slug works; gateway `do/openai` should also work if keys match |
| **Known limitation** | `502` / `504` / empty error | Slug unavailable on tier—**not a gateway defect** if D02 and gateway `do/llama` pass |
| **Fail (key issue)** | `401` | Same as D01—fix key before any gateway scoring |

**Reasoning:** DO catalog lists many models; nano/preview tiers may be blocked while Llama 70B works. Gateway correctly retries on 5xx when this slug is a fallback in `smart/general`.

**Alternative slug test (Anthropic on DO):**

```bash
curl -s -w "\nHTTP_CODE:%{http_code}\n" \
  https://inference.do-ai.run/v1/chat/completions \
  -H "Authorization: Bearer $DO_MODEL_ACCESS_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic-claude-haiku-4.5",
    "messages": [{"role": "user", "content": "Say hi"}],
    "stream": false
  }' | jq
```

Same scoring: 200 = slug OK; 5xx on tier = document as upstream limitation.

---

## D04: Gateway route resolution

**Capability verified:** Gateway maps DO aliases to the same slugs tested directly above.

**Command (gateway must be running):**

```bash
export BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

curl -s "$BASE_URL/debug/routes/do/llama" | jq
curl -s "$BASE_URL/debug/routes/do/openai" | jq
curl -s "$BASE_URL/debug/routes/smart/general" | jq
```

**Pass criteria:**

| Alias | Expected first target | Reasoning |
|---|---|---|
| `do/llama` | `digitalocean` / `llama3.3-70b-instruct` | Must match D02 slug |
| `do/openai` | `digitalocean` / `openai-gpt-5-nano` | Must match D03 slug |
| `smart/general` | Primary `groq`; fallbacks include DO Llama, DO OpenAI, DO Anthropic | Fallback order drives resilience |

**If mismatch:** Update [`config/models.yaml`](config/models.yaml) and redeploy—gateway is config-driven.

---

## D05: Gateway DO alias

**Capability verified:** Full stack: HTTP API → registry → orchestrator → DO adapter → upstream.

**Command:**

```bash
curl -s -w "\nHTTP_CODE:%{http_code}\n" "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: do-eval-1" \
  -d '{"model":"do/llama","messages":[{"role":"user","content":"Say hi"}],"stream":false}' | jq
```

**Pass criteria:**

| Check | Expected | Reasoning |
|---|---|---|
| HTTP status | `200` | Same outcome as D02, routed through gateway |
| `model` | `"llama3.3-70b-instruct"` | Upstream ID in response—proves adapter passed correct slug |
| Header `X-Routed-Provider` | `digitalocean` | Orchestrator recorded DO as winner |
| Header `X-Request-Id` | `do-eval-1` | Trace ID preserved |

**Compare D02 vs D05:**

| D02 | D05 | Conclusion |
|---|---|---|
| Pass | Pass | Gateway DO integration correct |
| Pass | Fail | Gateway env, adapter, or deploy issue |
| Fail | Fail | Fix DO key/tier first (not gateway) |
| Fail | Pass | Unlikely—recheck D02 key used |

---

## Decision tree (evaluator)

```text
Gateway do/llama failed?
├── D02 direct DO failed?  → Fix DO_MODEL_ACCESS_KEY / DO tier
├── D02 pass, D04 wrong slug? → Config/deploy issue (models.yaml)
├── D02 pass, D04 OK, D05 fail? → Gateway logs: adapter/orchestrator
└── D05 pass → DO path accepted ✓

Gateway do/openai failed but do/llama pass?
└── Run D03 → 5xx = upstream tier limitation (document, do not fail gateway)
```

---

## Logical aliases (DO-related)

| Alias | Upstream slug | Fallbacks |
|---|---|---|
| `do/llama` | `llama3.3-70b-instruct` | — |
| `do/openai` | `openai-gpt-5-nano` | — |
| `do/anthropic` | `anthropic-claude-haiku-4.5` | — |
| `smart/general` | Groq primary | DO Llama → DO OpenAI → DO Anthropic |

---

## Security notes for evaluators

- Do **not** put DO keys in `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` unless testing native provider URLs—the gateway reads `DO_MODEL_ACCESS_KEY` for the `digitalocean` provider.
- Keep secrets in `.env` only; [`.env.example`](.env.example) uses placeholders.
- `/debug/complete` and `/v1/chat/completions` share the same orchestrator—either proves full fallback chain; prefer `/v1/chat/completions` for OpenAI-compatible evaluation.

---

## Full gateway test suite

For non-DO-specific tests (Groq, streaming, errors, circuit breaker, pytest), use [`testing-e2e.md`](testing-e2e.md).

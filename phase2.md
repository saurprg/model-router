# Phase 2 — Cross-cutting Concerns (Deferred)

> **Status: ON HOLD** — Auth and middleware are deferred until **after core features** (Phases 3–7: routing, adapters, streaming, orchestrator, chat API) are working. Add this layer on top once the gateway demo is end-to-end.

Related docs: [`implementation_steps.md`](implementation_steps.md) · [`scope.md`](../scope.md)

---

## Why defer

- Faster iteration while building routing, adapters, and fallbacks (no `Authorization` header on every curl).
- Auth is additive — middleware wraps existing routes without changing orchestrator/adapter logic.
- `GATEWAY_API_KEY` is already in [`app/settings.py`](app/settings.py) and [`.env.example`](.env.example); ready when needed.

## Revised build order (skip Phase 2 for now)

```text
Phase 0 ✅ → Phase 1 ✅ → [Phase 2 DEFERRED] → Phase 3 → … → Phase 7
```

After Phase 7 demo works, return here and implement Phase 2 before any production hardening.

---

## What Phase 2 delivers (when implemented)

| Component | File | Responsibility | Priority |
|---|---|---|---|
| Request ID middleware | `app/middleware/request_id.py` | UUID trace ID, `X-Request-Id` header | Recommended first |
| Auth middleware | `app/middleware/auth.py` | `Authorization: Bearer <GATEWAY_API_KEY>` | After core demo |
| Wiring | `app/main.py` | Register middleware in correct order | Both |
| DI helper | `request_id.py` | `get_request_id()` for Phase 7 handlers | With request ID |

**Time estimate:** ~15 min total when resumed.

---

## Request flow (target state)

```mermaid
sequenceDiagram
  participant Client
  participant ReqId as RequestIdMiddleware
  participant Auth as AuthMiddleware
  participant App as FastAPI routes

  Client->>ReqId: HTTP request
  ReqId->>ReqId: request_id = uuid4()
  ReqId->>Auth: forward request
  alt public path /health /docs
    Auth->>App: pass through
  else protected path
    alt valid Bearer token
      Auth->>App: pass through
    else missing or invalid token
      Auth->>Client: 401 JSON + X-Request-Id
    end
  end
  App->>ReqId: response
  ReqId->>Client: response + X-Request-Id header
```

---

## Step 2.1 — Request ID middleware (~7 min)

**File:** `app/middleware/request_id.py`

**Pattern:** Starlette `BaseHTTPMiddleware`

```python
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")
```

### Design decisions

- Accept inbound `X-Request-Id` if client sends one; otherwise generate `uuid4()`.
- Always echo ID on response — including 401 from auth (requires middleware order below).
- `get_request_id()` dependency for `POST /v1/chat/completions` logging in Phase 7+.

---

## Step 2.2 — Auth middleware (~7 min) — DEFERRED

**File:** `app/middleware/auth.py`

**Pattern:** Starlette middleware with path allowlist

### Public paths (no auth required)

| Path | Reason |
|---|---|
| `/health` | Load balancer / k8s probe |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | OpenAPI schema |
| `/docs/oauth2-redirect` | FastAPI OAuth redirect |

```python
PUBLIC_PATHS = {"/health", "/openapi.json", "/docs/oauth2-redirect"}
PUBLIC_PREFIXES = ("/docs", "/redoc")
```

### Implementation sketch

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from app.settings import get_settings


class AuthMiddleware(BaseHTTPMiddleware):
    def _is_public(self, path: str) -> bool:
        if path in PUBLIC_PATHS:
            return True
        return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._is_public(request.url.path):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        expected = f"Bearer {get_settings().gateway_api_key}"
        if auth != expected:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "message": "Invalid or missing gateway API key",
                        "type": "AuthenticationError",
                        "code": "unauthorized",
                    }
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)
```

### Design decisions

- 401 JSON matches `error_payload` shape in `app/errors.py`.
- Post-MVP: use `secrets.compare_digest` for token comparison.
- Gateway key from `get_settings().gateway_api_key` (`.env`: `GATEWAY_API_KEY`).

---

## Step 2.3 — Wire middleware in main.py (~3 min)

**Middleware order (critical):** Starlette runs middleware in **reverse** order of `add_middleware` on incoming requests.

To get `RequestId → Auth → route`:

```python
from app.middleware.auth import AuthMiddleware
from app.middleware.request_id import RequestIdMiddleware

def create_app() -> FastAPI:
    app = FastAPI(title="Model Router", lifespan=lifespan)
    register_exception_handlers(app)

    app.add_middleware(AuthMiddleware)       # inner — runs second on incoming
    app.add_middleware(RequestIdMiddleware)  # outer — runs first on incoming

    ...
```

RequestId must be outer so **401 responses include `X-Request-Id`**.

---

## Step 2.4 — Package exports (optional)

**File:** `app/middleware/__init__.py`

```python
from app.middleware.auth import AuthMiddleware
from app.middleware.request_id import RequestIdMiddleware, get_request_id

__all__ = ["AuthMiddleware", "RequestIdMiddleware", "get_request_id"]
```

---

## Verification checklist (when resumed)

Server: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

### Health and docs stay public

```bash
curl -i http://127.0.0.1:8000/health
# 200, X-Request-Id, no Authorization

curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/docs
# 200
```

### Protected routes (use `/v1/chat/completions` or temp `/v1/ping`)

```bash
curl -i http://127.0.0.1:8000/v1/ping
# 401 + error JSON + X-Request-Id

curl -i -H "Authorization: Bearer dev-gateway-key-change-me" http://127.0.0.1:8000/v1/ping
# 200 + X-Request-Id

curl -i -H "Authorization: Bearer wrong-key" http://127.0.0.1:8000/v1/ping
# 401
```

### Optional automated tests

**File:** `tests/test_auth.py` — TestClient asserts public paths, 401/200 on protected paths, `X-Request-Id` on all responses.

---

## Files to change (when resumed)

| File | Action |
|---|---|
| `app/middleware/request_id.py` | Implement |
| `app/middleware/auth.py` | Implement |
| `app/middleware/__init__.py` | Export symbols |
| `app/main.py` | Register middleware |
| `tests/test_auth.py` | Optional |

No changes needed to `app/settings.py` — `gateway_api_key` already defined.

---

## Pitfalls to avoid

1. **Wrong middleware order** — Auth must be inner, RequestId outer.
2. **Forgetting OpenAPI paths** — `/openapi.json` and `/docs/oauth2-redirect` must stay public.
3. **Bearer format** — exactly `Bearer <key>` with one space.
4. **curl from host** — use integrated terminal / `127.0.0.1:8000` inside dev container.

---

## When to implement

| Trigger | Action |
|---|---|
| Phase 7 E2E demo works (stream + fallback) | Implement Step 2.1 (request ID) first — helps logging |
| Before sharing externally / production | Implement Step 2.2 (auth) — required |
| Before CI/deploy | Add `tests/test_auth.py` |

---

## Resume checklist

```text
[ ] Implement RequestIdMiddleware + get_request_id()
[ ] Implement AuthMiddleware + public path allowlist
[ ] Wire middleware in main.py (correct order)
[ ] Verify curl checks
[ ] Optional: tests/test_auth.py
[ ] Mark Phase 2 complete in implementation_steps.md
```

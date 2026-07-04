# Phase 3 — Routing Registry

> **Status:** Implemented. Maps logical model aliases to ordered upstream `{ provider, model }` targets.

Related: [`implementation_steps.md`](implementation_steps.md) · [`phase2.md`](phase2.md) (deferred)

---

## Goal

Load [`config/models.yaml`](config/models.yaml) once at startup. Expose `ModelRegistry` for Phase 4+ orchestrator and adapters.

| Method | Returns |
|---|---|
| `resolve(logical_model)` | `[RouteTarget, ...]` — primary first, then fallbacks |
| `get_provider(name)` | `ProviderConfig` — base URL + API key env var |
| `list_logical_models()` | Sorted alias names for `/v1/models` (Phase 7) |

**Routing MVP:** alias-only (`smart/general`). Unknown model → `UnknownModelError` (404).

---

## Files

| File | Role |
|---|---|
| `config/models.yaml` | Static routes + provider definitions |
| `app/router/registry.py` | `ModelRegistry`, dataclasses, `get_registry()` |
| `app/router/__init__.py` | Public exports |
| `app/main.py` | `app.state.registry` in lifespan; `/debug/routes/{model}` |
| `tests/test_registry.py` | Unit tests |

---

## Verify

```bash
cd /workspaces/model-router
source .venv/bin/activate
pytest tests/test_registry.py -q
curl http://127.0.0.1:8000/debug/routes/smart/general
```

---

## Next: Phase 4

Implement `app/providers/base.py` and `openai_adapter.py` using `RouteTarget` + `ProviderConfig`.

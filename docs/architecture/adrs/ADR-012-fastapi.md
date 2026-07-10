# ADR-012: FastAPI as the API Core Framework

## Status
* **Status:** Accepted
* **Date:** 2026-07-10 (migrated from legacy 06_ARCHITECTURE_DECISION_RECORDS.md ADR-01)
* **Original Date:** Phase 0 (Foundation)
* **Author:** Architecture Team
* **Migration Note:** This ADR was originally filed in legacy single-file format at `docs/06_ARCHITECTURE_DECISION_RECORDS.md` as "ADR-01: Selection of FastAPI for API Core". Migrated to canonical Nygard format on 2026-07-10 during documentation governance cleanup (Phase A → Phase E).

---

## Context

JARVIS OS requires a backend that:

- Supports **asynchronous execution** natively (event loops must not be blocked by I/O, request handlers, or websocket fan-out).
- Provides **WebSocket support** for live execution streaming (Phase 27 spec mandates SSE/WebSocket transports).
- Generates **automatic OpenAPI / Swagger** documentation so external integrators can discover the API surface without reading source.
- Plays well with **async database drivers** (`asyncpg` for PostgreSQL, redis.asyncio for Redis pub/sub).
- Allows tight Pydantic DTO integration at the request/response boundary.

Synchronous frameworks (Flask, Django, plain WSGI) were ruled out at Phase 0 because they cannot satisfy the async + WebSocket + auto-doc requirements simultaneously without significant glue code.

---

## Decision

**Use FastAPI (Python 3.11+) as the API core framework for JARVIS OS.**

Key decisions:

- **ASGI backend:** `uvicorn` workers behind `uvloop` for low-latency event loops.
- **Async everywhere:** every endpoint handler is `async def`; no blocking calls in request path.
- **Pydantic for DTOs:** request and response schemas are Pydantic models (also reused in `core/` — DTO-First rule).
- **WebSockets:** native FastAPI WebSocket route handlers for live execution streaming (Phase 27).
- **OpenAPI:** auto-generated at `/openapi.json` and `/docs`; frozen per Phase 14.
- **Route organization:** routers per domain (`api/agent/`, `api/memory/`, `api/skill/`, `api/admin/`) — see `docs/architecture/10_REPOSITORY_LAYOUT_FREEZE.md`.

---

## Consequences

### Positive

- **Low overhead routing** — Starlette ASGI core, ~3-5× faster than Flask for the same workload.
- **Native async** — `asyncpg`, `redis.asyncio`, async ORM all work without threadpool offload.
- **WebSockets are first-class** — no separate library (no `websockets-asyncio` glue).
- **Auto OpenAPI** — single source of truth (Pydantic) generates both validation and documentation.
- **Type safety** — `mypy --strict` end-to-end through handler signature.

### Negative

- **No batteries-included admin UI** (unlike Django) — admin endpoints built manually.
- **Pydantic v1/v2 migration** — past baggage; current target is Pydantic v2 only.
- **Relatively young framework** — fewer StackOverflow answers than Flask for edge cases (mitigated by active community).
- **ASGI-only** — cannot run on legacy WSGI hosts; requires `uvicorn`/`hypercorn`/similar.

### Risks

- Async/await pitfalls in third-party libraries (mitigated by `core/` boundary enforcing async-only repos).

---

## Compliance & Invariants

- All API handlers MUST be `async def`. Synchronous handlers are not allowed in `api/**`.
- All request/response DTOs MUST be Pydantic models.
- OpenAPI schema MUST be regenerated on every API change and checked into `docs/architecture/02_API_CONTRACTS_FREEZE.md` references.
- WebSocket handlers MUST include connection-level ping/pong (see Phase 27 spec §heartbeat).

---

## Related

- `docs/architecture/02_API_CONTRACTS_FREEZE.md` — frozen API contract schemas
- `docs/architecture/10_REPOSITORY_LAYOUT_FREEZE.md` — `api/` directory layout
- `docs/34_API_STANDARD.md` — REST/WebSocket conventions
- Phase 14 spec — API Gateway layer
- Phase 27 spec — live execution streaming

---

## References

- Original entry: `docs/06_ARCHITECTURE_DECISION_RECORDS.md` ADR-01 (preserved for audit trail)
- Migration record: `.audit/CLEANUP_REPORT.md` (Phase E — 2026-07-10)

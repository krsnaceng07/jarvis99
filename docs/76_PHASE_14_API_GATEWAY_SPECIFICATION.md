# 76_PHASE_14_API_GATEWAY_SPECIFICATION.md

## Purpose
This document establishes the Frozen Architecture Specification for **Phase 14: API Gateway Layer**. It exposes the frozen Phase 1–13 core (`ReasoningExecutionEngine`, `WorkflowOrchestrator`, `HealthMonitor`) behind a FastAPI HTTP + WebSocket gateway, strictly conforming to the frozen REST/WS envelopes. Any modification to these components requires a formal Change Request (CR).

## Status
**STATUS: APPROVED_FOR_IMPLEMENTATION**
Approved by Architecture Gatekeeper after frozen-contract conflict resolution (2026-06-28).
Authority rank: 3 (Phase Master Specification) per `AGENTS.md` §1.

---

## Architecture Position

```
HTTP / WebSocket clients
        │  (frozen envelope: 02_API_CONTRACTS_FREEZE.md)
        ▼
api/  (Phase 14 — NEW, this spec)
   ├── main.py              ← FastAPI app factory + lifespan (Kernel boot/shutdown)
   ├── dependencies.py      ← DI: resolve singletons from Kernel.container
   ├── middleware.py         ← envelope injection (timestamp, request_id)
   ├── dto.py               ← Pydantic DTOs + envelopes (immutable contracts)
   ├── stream_service.py    ← WebSocket hub broadcasting EventBus topics
   └── routes/
       ├── health.py        ← GET /api/v1/health
       ├── agent.py         ← POST /api/v1/agent/run  +  GET /api/v1/agent/runs/{id}
       └── workflow.py      ← POST /api/v1/workflows  +  GET /api/v1/workflows/{id}
        │
        ▼  (resolve from Kernel.container — never instantiate core/ directly)
core/  (Phases 1–13 — FROZEN, unchanged)
   ├── ReasoningExecutionEngine.execute_goal(goal, budget) -> Dict
   ├── WorkflowOrchestrator.execute_workflow(compiled, session) -> Dict
   ├── WorkflowValidator / WorkflowCompiler / WorkflowRepository
   └── HealthMonitor.check_health() -> Dict
```

**Dependency direction (frozen, rank 2):** `api/ → core/`. `core/` MUST NOT import `api/`. Enforced by §6 STOP + Quality Gate architecture audit.

---

## Frozen Constraints (non-negotiable)

| # | Constraint | Frozen source |
|---|------------|---------------|
| C1 | Every REST response wrapped in `{success, data, meta{timestamp, request_id}}` | `docs/architecture/02` §1 |
| C2 | Every error response wrapped in `{success:false, error{code,message,details}, meta}` | `docs/architecture/02` §2 |
| C3 | Every WebSocket frame uses `{event, payload, timestamp}` | `docs/architecture/02` §3 |
| C4 | `api/` resolves all core services from `Kernel.container`; never instantiates core classes directly | `docs/architecture/08` §1 + DI |
| C5 | `core/` never imports `api/` | `docs/architecture/01` (layer direction) |
| C6 | No core/ file modified (Phase 1–13 frozen) | `docs/74`, `docs/75` |
| C7 | Error `details` never expose stack traces, file paths, or credentials | `docs/architecture/02`, `docs/34` |
| C8 | External packages must be declared in `pyproject.toml` before use | Constitution Rule 14 |

---

## Dependency Manifest Update (Milestone 0 — pre-implementation)

Add to `pyproject.toml` `[project].dependencies`:
```toml
"fastapi>=0.115.0",
"uvicorn[standard]>=0.32.0",
"websockets>=13.0",
```
Rationale: satisfies Constitution Rule 14 (no hidden deps) + `docs/34` FastAPI mandate. This is an L2 change per `docs/architecture/07` (declared, audited).

---

## DTO Contracts (`api/dto.py`)

All DTOs are Pydantic v2 `BaseModel`. Response envelopes are generic. **10 DTOs total** (8 payload + 2 envelope).

### Request DTOs
```python
class AgentRunRequest(BaseModel):
    goal: str                          # non-empty, max 4000 chars
    budget: float = Field(default=10.0, ge=0.0, le=1000.0)

class WorkflowSubmitRequest(BaseModel):
    name: str                          # non-empty
    steps: list[WorkflowStep]          # re-export from core.tools.workflow_dto
    version: int = Field(default=1, ge=1)
```

### Response payload DTOs (the `data` field inside success envelope)
```python
class AgentRunAcceptedResponse(BaseModel):
    run_id: UUID
    status: str = "accepted"           # async-accepted: actual run via BG task / WS
    trace_id: UUID

class AgentRunStatusResponse(BaseModel):
    run_id: UUID
    state: SessionState                # re-export from core.reasoning.engine_dto
    metrics: dict | None = None        # EngineMetrics.model_dump() when completed
    failure_type: FailureType | None = None

class WorkflowSubmitResponse(BaseModel):
    workflow_id: UUID
    version: int
    status: WorkflowState = WorkflowState.PENDING

class WorkflowStatusResponse(BaseModel):
    workflow_id: UUID
    state: WorkflowState
    metrics: dict | None = None        # WorkflowMetrics.model_dump()

class HealthResponse(BaseModel):
    status: str                        # "healthy" | "degraded"
    uptime_seconds: float
    connectivity: dict[str, str]       # {"database": "OK"|"ERROR", "redis": ...}
    resources: dict[str, float]        # disk_percent, disk_free_gb, cpu, memory
```

### Error DTO (the `error` field inside error envelope)
```python
class ErrorDetail(BaseModel):
    code: str                          # JarvisError.code, e.g. "SYSTEM_999"
    message: str                       # human-readable, no stack trace
    details: dict = Field(default_factory=dict)
```

### Envelope DTOs (the frozen wrappers — REQUIRED by C1/C2)
```python
class MetaBlock(BaseModel):
    timestamp: datetime                # ISO-8601 UTC
    request_id: UUID

class SuccessEnvelope(BaseModel, generic=T):
    success: Literal[True] = True
    data: T
    meta: MetaBlock

class ErrorEnvelope(BaseModel):
    success: Literal[False] = False
    error: ErrorDetail
    meta: MetaBlock
```
*Implementation note:* Pydantic v2 generic envelope via `TypeVar` bound; concrete instances constructed in route handlers. Immutability not required on envelopes (they are transport wrappers), but payload DTOs follow `docs/75` immutability norms where they mirror frozen core DTOs.

---

## API Routes

All routes prefixed `/api/v1`. All success responses return `SuccessEnvelope`; all errors return `ErrorEnvelope` with correct HTTP status.

| Method | Path | Handler | Returns (data) | HTTP |
|--------|------|---------|----------------|------|
| GET | `/api/v1/health` | `routes.health.health` | `HealthResponse` | 200 / 503 |
| POST | `/api/v1/agent/run` | `routes.agent.run_agent` | `AgentRunAcceptedResponse` | 202 |
| GET | `/api/v1/agent/runs/{run_id}` | `routes.agent.get_run_status` | `AgentRunStatusResponse` | 200 / 404 |
| POST | `/api/v1/workflows` | `routes.workflow.submit_workflow` | `WorkflowSubmitResponse` | 202 |
| GET | `/api/v1/workflows/{workflow_id}` | `routes.workflow.get_workflow_status` | `WorkflowStatusResponse` | 200 / 404 |
| WS | `/ws/v1/telemetry` | `stream_service.telemetry_hub` | `{event, payload, timestamp}` frames | — |

### Route handler rules
- Handlers are thin: validate request → resolve service from DI (`Depends`) → call core method → wrap in envelope. **No business logic in routes** (Constitution Rule 11).
- `POST /agent/run` is **async-accepted (202)**: it enqueues a background task calling `ReasoningExecutionEngine.execute_goal()` and returns `run_id` immediately. Long-running goals must not block the HTTP request.
- `POST /workflows` validates+compiles via frozen `WorkflowValidator`/`WorkflowCompiler`, persists via `WorkflowRepository`, returns `workflow_id`. Execution is a separate explicit action (Phase 14 implements submit + status only; execution trigger is out of scope — see §Scope Boundary).

---

## Streaming Rules (WebSocket per frozen 02_CONTRACTS §3)

`api/stream_service.py` implements a `TelemetryHub`:
- Endpoint: `ws://host/ws/v1/telemetry`
- On client connect: subscribes a callback to the `EventBusInterface` (resolved from `Kernel.container`) for the topics in §Event Whitelist.
- On each EventBus message: serializes to frozen frame `{event, payload, timestamp}` and sends to the connected client.
- On disconnect: unsubscribes the callback (no leak).
- Hub holds an in-memory registry of active connections (`set[WebSocket]`); broadcasts are `asyncio.gather` over connections with per-connection error isolation.

**Forbidden:** SSE. SSE is NOT a frozen contract and is out of scope for Phase 14.

---

## Background Job State Machine (async-accepted runs)

For `POST /agent/run` (and future workflow execution):

| State | Meaning | Transition trigger |
|-------|---------|--------------------|
| `QUEUED` | Accepted, not started | 202 response emitted |
| `RUNNING` | `execute_goal` invoked | BG task starts |
| `COMPLETED` | core returned `status=SUCCESS` | BG task finishes |
| `FAILED` | core returned `status=FAILURE` | BG task catches |
| `NOT_FOUND` | run_id unknown | status query miss |

Storage: in-memory `dict[UUID, AgentRunStatusResponse]` in `dependencies.py` for Phase 14. **Database persistence of runs is out of scope** (reserved for a later phase) — see §Scope Boundary.

---

## Error Envelope Mapping

`api/middleware.py` registers a global exception handler mapping frozen `JarvisError` subclasses → `ErrorEnvelope`:

| Exception (frozen, `core/exceptions.py`) | HTTP | `error.code` prefix |
|------------------------------------------|------|---------------------|
| `JarvisSystemError` | 500 | `SYSTEM_*` |
| `JarvisMemoryError` | 503 | `MEMORY_*` |
| `JarvisAgentError` / `JarvisSkillError` | 422 / 500 | `AGENT_*` / `SKILL_*` |
| `BudgetExceededError` | 402 | `MODEL_*` (budget) |
| `RateLimitError` | 429 | `MODEL_*` (rate) |
| `AuthenticationError` | 401 | `MODEL_*` (auth) |
| `TimeoutError` | 504 | `MODEL_*` (timeout) |
| `ValidationError` (Pydantic/FastAPI) | 422 | `VALIDATION_*` |
| Unhandled `Exception` | 500 | `SYSTEM_999` (generic, sanitized) |

`details` MUST contain no stack trace, file path, or credential (C7). `request_id` and `timestamp` always populated by middleware.

---

## Event Whitelist (WebSocket broadcast topics)

Only these EventBus topics (from frozen `core/`) are forwarded to WS clients:
- `engine.state.transition` (Phase 12)
- `workflow.started`, `workflow.completed`, `workflow.step.started`, `workflow.step.completed`, `workflow.step.failed` (Phase 13)
- `system.kernel.ready` (Kernel)
- `tool.spawn.started`, `tool.completed`, `tool.failed`, `tool.approval.waiting` (Phase 11)

Any topic not in this list is NOT forwarded (least-privilege surface). Adding a topic requires a CR.

---

## Health Endpoint Contract

`GET /api/v1/health` resolves `HealthMonitor` from DI and calls `await health_monitor.check_health()`. Maps the returned dict to `HealthResponse`:
- `status == "healthy"` → HTTP 200, envelope `success=true`.
- `status == "degraded"` → HTTP **503**, envelope `success=true` (data is valid; the *service* signals degraded, not the HTTP call). This distinction is documented for clients.

---

## Test Requirements

`tests/test_api_gateway.py` (and per-route files if split). Coverage target per `docs/47`: **≥ 80% general, 100% for `middleware.py` (error sanitization is security-adjacent)**.

Mandatory test cases:
1. Each route returns correct envelope shape (success + meta populated).
2. `POST /agent/run` returns 202 + `run_id`; subsequent `GET` returns state progression.
3. `POST /workflows` rejects invalid plan (validator path) with 422 envelope.
4. Error middleware sanitizes: a raised `JarvisMemoryError` with sensitive `details` does NOT leak to client.
5. WebSocket hub: connecting client receives a forwarded `engine.state.transition` frame in frozen shape.
6. DI: routes fail fast (clean error) if `Kernel.container` is not booted — no silent None dereference.
7. Layer audit test: `core/` contains zero imports of `api/` (architecture gate).
8. Health degraded → 503 path.

Tests must NOT instantiate real LLM/network — mock `ReasoningExecutionEngine`, `WorkflowOrchestrator`, `EventBusInterface` via the DI container.

---

## Scope Boundary (explicit non-goals for Phase 14)

To prevent scope creep (the #1 risk per governance review):
- ❌ No database persistence of runs/workflow executions (in-memory status only).
- ❌ No workflow *execution* trigger endpoint (submit + status only).
- ❌ No SSE streaming.
- ❌ No authentication/authorization layer (reserved — security phase).
- ❌ No modifications to any `core/` file.
- ❌ No new EventBus topics.
Any of these discovered mid-implementation → §STOP (AGENTS.md §6 condition #2 scope divergence).

---

## Implementation Milestones (ordered — AGENTS.md §5 lifecycle)

| Milestone | Files | Gate |
|-----------|-------|------|
| M0 | `pyproject.toml` (deps add) | ruff + install verifies |
| M1 | `api/__init__.py`, `api/dto.py` (10 DTOs) | ruff + mypy + unit tests on DTOs |
| M2 | `api/dependencies.py` (DI from Kernel.container) | mypy + unit (resolve returns singletons) |
| M3 | `api/middleware.py` (envelope + error mapping) | mypy + 100% coverage (sanitization) |
| M4 | `api/routes/health.py` | ruff + mypy + route test |
| M5 | `api/routes/agent.py` + BG state machine | route tests (202 + status) |
| M6 | `api/routes/workflow.py` (submit + status) | route tests (validate path) |
| M7 | `api/stream_service.py` (WS hub) | WS frame shape test |
| M8 | `api/main.py` (app factory + lifespan) | app boots, health 200 |
| M9 | `tests/test_api_gateway.py` (full + layer audit) | ≥80% / 100% middleware |
| M10 | Final Gate + Walkthrough + Freeze | full suite, 0 regression |

Each milestone emits `AGENTS.md` §10 MILESTONE REPORT and stops for approval before the next.

---

## Architecture Invariants (must never be violated by CR)

| Invariant | Enforcement |
|-----------|-------------|
| All responses conform to frozen envelope (02_CONTRACTS) | middleware + OpenAPI check in gate |
| `api/` never instantiates core classes directly | DI resolution only; lint test |
| `core/` never imports `api/` | layer audit test (M9 #7) |
| No `core/` file modified in Phase 14 | git diff check at freeze |
| Error `details` sanitized | 100% middleware coverage |
| WS frames match frozen §3 shape | M7 test |

---

## Future Change Control Process (CR)

To modify any Phase 14 component, a formal Change Request must be proposed:
1. **Propose:** Declare `CR-XXX` with reasoning, files affected, risks, benefits.
2. **Review:** Architecture Gatekeeper reviews for envelope compliance, layer direction, DI integrity, and frozen Phase 1–13 boundary.
3. **Approve:** This spec's STATUS updated to FROZEN only after full gate + human Gatekeeper approval.

---

## Related Documents
- [AGENTS.md](../AGENTS.md) — canonical entry-point (authority rank 7)
- [60_MASTER_INDEX.md](60_MASTER_INDEX.md) — documentation index
- [74_PHASE_1_12_MASTER_SPECIFICATION.md](74_PHASE_1_12_MASTER_SPECIFICATION.md) — frozen core baseline
- [75_PHASE_13_MASTER_SPECIFICATION.md](75_PHASE_13_MASTER_SPECIFICATION.md) — frozen workflow baseline
- [architecture/02_API_CONTRACTS_FREEZE.md](architecture/02_API_CONTRACTS_FREEZE.md) — envelope contracts (rank 2)
- [architecture/08_COMPONENT_INTERFACE_FREEZE.md](architecture/08_COMPONENT_INTERFACE_FREEZE.md) — Kernel/EventBus interfaces
- [34_API_STANDARD.md](34_API_STANDARD.md) — FastAPI + envelope standard
- [47_QUALITY_GATES.md](47_QUALITY_GATES.md) — gate matrix

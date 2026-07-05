# 88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 27: Observability, Cost Governance & Live Execution Streaming**. It implements a real-time telemetry layer, a cost governor that enforces LLM API budget constraints, and a WebSocket streaming endpoint that allows external consumers to observe JARVIS execution in real time.

## Status
**STATUS:** SPECIFICATION (PROPOSED)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phases 1–26

---

## 1. Architectural Position

Phase 27 adds the **Observability Layer** — a cross-cutting concern that sits above the existing runtime stack without touching any frozen interface:

```
                    External Clients (Dashboard / CLI / Monitoring)
                                        │
                            WebSocket /ws/v1/telemetry/stream
                                        │
                              ┌─────────┴─────────┐
                              ▼                   ▼
                     TelemetryBroadcaster   MetricsCollector
                    (WebSocket fan-out)   (Prometheus endpoint)
                              │                   │
                    ┌─────────┴─────────┐         │
                    ▼                   ▼         ▼
             ExecutionTracer       CostGovernor  HealthProbe
          (Span lifecycle hooks)  (Budget rules)  (Heartbeat)
                    │                   │
                    ▼                   ▼
              SpanRepository      BudgetRepository
           (SQLite/PostgreSQL)   (SQLite/PostgreSQL)
```

The layer is **additive-only**. It hooks into existing components via the event bus (`SwarmMessageBus` / `EventBus`) — **never** by modifying frozen interfaces.

---

## 2. Scope & Boundaries

### In Scope
- **ExecutionTracer:** Subscribes to the event bus and records lifecycle spans (task start → completion/failure). Persists `TraceSpan` records to the database.
- **CostGovernor:** Intercepts LLM token usage events, accumulates daily cost, enforces three budget tiers: Warning (80%), Block ($0.50/call), Exhaustion (failover to local model). Budget state is persisted to the database.
- **TelemetryBroadcaster:** WebSocket endpoint at `/ws/v1/telemetry/stream` that fans out a structured JSON envelope to all connected clients every 2 seconds (throttled per `docs/39_OBSERVABILITY_STANDARD.md`).
- **MetricsCollector:** Prometheus-compatible `/metrics` HTTP endpoint exposing gauge metrics (agent count, queue depth, token cost/day, error rate).
- **HealthProbe:** A background coroutine that emits kernel heartbeats every 10 seconds into the event bus. Marks components `OFFLINE` if heartbeat is missing for 30 seconds (per `docs/39_OBSERVABILITY_STANDARD.md`).
- **BudgetRepository:** SQLAlchemy-backed persistence adapter for daily cost ledger entries and token usage logs.
- **SpanRepository:** SQLAlchemy-backed persistence adapter for execution trace spans.
- **REST Endpoints:**
  - `GET /api/v1/observability/traces` — Paginated query for trace spans.
  - `GET /api/v1/observability/budget` — Current daily cost summary.
  - `GET /api/v1/observability/health` — Kernel and component health status.

### Out of Scope (Non-Goals)
- ❌ Modifying `AgentLoop`, `SwarmOrchestrator`, `LlmRuntime`, or any frozen interface.
- ❌ Building a full frontend UI dashboard (deferred to a later phase).
- ❌ Distributed tracing across multiple hosts (single-node scope).
- ❌ Real-time model cost API lookups (pricing is configurable static mapping).

---

## 3. Database Schema Specifications

### 3.1 Trace Spans Table (`trace_spans`)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `span_id` | `Uuid` | Primary Key | Unique span identifier |
| `trace_id` | `Uuid` | Not Null, Indexed | Parent trace group identifier |
| `parent_span_id` | `Uuid` | Nullable | Parent span for nested calls |
| `component` | `String(100)` | Not Null | Source component name (e.g. `AgentLoop`, `SwarmOrchestrator`) |
| `operation` | `String(255)` | Not Null | Operation name (e.g. `task.start`, `llm.call`, `tool.execute`) |
| `status` | `String(50)` | Not Null | `STARTED`, `COMPLETED`, `FAILED`, `CANCELLED` |
| `duration_ms` | `Float` | Nullable | Elapsed duration in milliseconds |
| `metadata` | `JSONB` | Nullable | Non-sensitive context (task_id, executor type, retry count) |
| `error` | `String(1000)` | Nullable | Truncated error message on failure |
| `started_at` | `DateTime` | Not Null, Default UTC | Span start timestamp |
| `ended_at` | `DateTime` | Nullable | Span end timestamp |

### 3.2 Budget Ledger Table (`budget_ledger`)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | PK, Autoincrement | Row ID |
| `date` | `String(10)` | Not Null, Indexed | Date key `YYYY-MM-DD` |
| `model` | `String(100)` | Not Null | LLM model identifier |
| `input_tokens` | `Integer` | Not Null, Default 0 | Cumulative input tokens for date/model |
| `output_tokens` | `Integer` | Not Null, Default 0 | Cumulative output tokens for date/model |
| `cost_usd` | `Float` | Not Null, Default 0.0 | Cumulative USD cost for date/model |
| `call_count` | `Integer` | Not Null, Default 0 | Number of LLM API calls |
| `updated_at` | `DateTime` | Not Null | Last update timestamp |

### 3.3 Health States Table (`component_health`)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `component_id` | `String(100)` | Primary Key | Component identifier |
| `status` | `String(50)` | Not Null | `ONLINE`, `DEGRADED`, `OFFLINE` |
| `last_heartbeat` | `DateTime` | Not Null | Last received heartbeat timestamp |
| `metadata` | `JSONB` | Nullable | Optional diagnostic context |

---

## 4. Component Contracts

### 4.1 ExecutionTracer

```python
class ExecutionTracer:
    """Subscribes to the event bus and records lifecycle spans."""

    async def start_span(
        self,
        trace_id: UUID,
        component: str,
        operation: str,
        parent_span_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UUID:
        """Open a new span. Returns the span_id."""

    async def end_span(
        self,
        span_id: UUID,
        status: str,  # COMPLETED | FAILED | CANCELLED
        error: Optional[str] = None,
    ) -> None:
        """Close a span and persist to SpanRepository."""
```

### 4.2 CostGovernor

```python
class CostGovernor:
    """Enforces daily API budget constraints per docs/65_COST_GOVERNOR.md."""

    async def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> CostDecision:
        """
        Accumulate token usage and return a CostDecision.
        CostDecision indicates: ALLOW | WARN | BLOCK | FAILOVER.
        """

    async def estimate_cost(self, model: str, estimated_tokens: int) -> float:
        """Pre-call cost estimation in USD."""

    async def get_daily_summary(self) -> BudgetSummary:
        """Return current daily cost totals and tier status."""
```

**CostDecision Enum:**
```python
class CostDecision(str, Enum):
    ALLOW    = "ALLOW"     # Under 80% threshold — proceed normally
    WARN     = "WARN"      # 80–100% threshold — alert raised, proceed
    BLOCK    = "BLOCK"     # Single-call cost > $0.50 — pause for approval
    FAILOVER = "FAILOVER"  # Daily budget exhausted — route to local model
```

**BudgetSummary DTO:**
```python
class BudgetSummary(BaseModel):
    date: str                  # YYYY-MM-DD
    total_cost_usd: float      # Accumulated daily cost
    daily_limit_usd: float     # Configured max (default $10.00)
    warn_threshold_usd: float  # 80% of limit (default $8.00)
    tier: CostDecision         # Current tier
    call_count: int            # Number of LLM calls today
    total_tokens: int          # Combined input + output tokens
```

### 4.3 TelemetryBroadcaster

```python
class TelemetryBroadcaster:
    """WebSocket fan-out broadcaster for real-time telemetry."""

    async def connect(self, websocket: WebSocket) -> None:
        """Register a new WebSocket subscriber."""

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket subscriber."""

    async def broadcast(self, envelope: TelemetryEnvelope) -> None:
        """Send envelope to all connected subscribers."""
```

**TelemetryEnvelope DTO (streamed every 2 seconds):**
```python
class TelemetryEnvelope(BaseModel):
    timestamp: datetime
    active_agents: int
    queued_tasks: int
    completed_tasks: int
    failed_tasks: int
    cost_today_usd: float
    cost_tier: str           # ALLOW | WARN | BLOCK | FAILOVER
    component_health: Dict[str, str]  # component_id → status
    recent_spans: List[SpanSummary]   # Last 10 spans (non-sensitive)
```

### 4.4 HealthProbe

```python
class HealthProbe:
    """Emits and monitors component heartbeats per docs/39_OBSERVABILITY_STANDARD.md."""

    async def emit_heartbeat(self, component_id: str) -> None:
        """Update the last_heartbeat timestamp for a component."""

    async def check_all(self) -> Dict[str, str]:
        """Scan all registered components. Mark OFFLINE if heartbeat > 30s ago."""
```

### 4.5 Repository Contracts

```python
class SpanRepository:
    async def save(self, span: TraceSpanRecord, session: AsyncSession) -> None: ...
    async def list_paginated(self, limit: int, offset: int, session: AsyncSession) -> List[TraceSpanRecord]: ...

class BudgetRepository:
    async def upsert_ledger(self, date: str, model: str, tokens_in: int, tokens_out: int, cost: float, session: AsyncSession) -> None: ...
    async def get_daily_total(self, date: str, session: AsyncSession) -> float: ...
    async def get_summary(self, date: str, session: AsyncSession) -> BudgetSummary: ...
```

---

## 5. API Gateway Interface

### New REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/observability/traces` | Paginated trace spans (`limit`, `offset` query params) |
| `GET` | `/api/v1/observability/budget` | Current daily cost summary (`BudgetSummary`) |
| `GET` | `/api/v1/observability/health` | All component health states |
| `GET` | `/metrics` | Prometheus-compatible text exposition |

### New WebSocket Endpoint

| Protocol | Path | Description |
|----------|------|-------------|
| `WS` | `/ws/v1/telemetry/stream` | Real-time `TelemetryEnvelope` fan-out (2-second throttle) |

---

## 6. Integration Points (Event Bus Hooks)

Phase 27 integrates with existing systems **exclusively via event bus subscriptions** — no frozen file is modified:

| Event Topic | Subscriber | Action |
|-------------|------------|--------|
| `swarm.task.started` | `ExecutionTracer` | Open a new trace span |
| `swarm.task.completed` | `ExecutionTracer` | Close span with `COMPLETED` |
| `swarm.task.failed` | `ExecutionTracer` | Close span with `FAILED` |
| `llm.tokens.used` | `CostGovernor` | Accumulate usage, evaluate tier |
| `kernel.heartbeat` | `HealthProbe` | Update component health record |
| `observability.tick` | `TelemetryBroadcaster` | Assemble and broadcast `TelemetryEnvelope` |

> **New event topics** (`llm.tokens.used`, `kernel.heartbeat`, `observability.tick`) are published by the new Phase 27 components only — not added to any frozen file.

---

## 7. Pricing Configuration

Model pricing is stored in a static configurable mapping (not fetched live):

```python
MODEL_PRICING_USD_PER_1K_TOKENS: Dict[str, Dict[str, float]] = {
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-opus":      {"input": 0.015, "output": 0.075},
    "gpt-4o":             {"input": 0.005, "output": 0.015},
    "gpt-4-turbo":        {"input": 0.010, "output": 0.030},
    "gemini-1.5-pro":     {"input": 0.00125, "output": 0.005},
    "local":              {"input": 0.0, "output": 0.0},   # Ollama / vLLM
}
```

---

## 8. Security Considerations

- Telemetry payloads **must never include** raw prompt text, file content, database values, or secrets (per `docs/39_OBSERVABILITY_STANDARD.md`).
- `SpanRepository` metadata column is sanitized by the `ExecutionTracer` before insertion — any value matching the secret regex patterns from `docs/29_SECRET_MANAGEMENT.md` is replaced with `<redacted>`.
- The `/ws/v1/telemetry/stream` endpoint requires the same auth token as existing API endpoints (deferred to Phase 28 auth integration if auth is not yet wired; endpoint returns 401 if auth middleware is active).
- Budget limits are read from Pydantic Settings (`JARVIS_DAILY_BUDGET_USD`) — agents cannot modify them at runtime.

---

## 9. Verification and Acceptance Criteria

### Automated Test Requirements
- **Span lifecycle tests:** `start_span` → `end_span` round-trip with correct DB persistence; error propagation.
- **CostGovernor tier tests:** All four tiers (`ALLOW`, `WARN`, `BLOCK`, `FAILOVER`) exercised with mocked token usage accumulation.
- **BudgetRepository upsert tests:** Idempotent accumulation across multiple calls for same date/model.
- **TelemetryBroadcaster tests:** Connect/disconnect/broadcast fan-out verified with mock WebSockets.
- **HealthProbe tests:** Heartbeat emission, ONLINE → OFFLINE state transition on stale heartbeat.
- **REST endpoint tests:** All four GET endpoints return correct schema; 404/empty states handled.
- **Integration test:** Full event-bus round-trip: publish `swarm.task.started` → verify span created in DB.
- **All Quality Gates Pass:** Zero lint errors, strict MyPy, zero regressions (1005/1005 tests pass + new tests).

### Target Test Count
- ≥ **25 new tests** across all Phase 27 components.
- Total system: **≥ 1030 tests passing**.

---

## 10. Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [39_OBSERVABILITY_STANDARD.md](file:///e:/jarvis/docs/39_OBSERVABILITY_STANDARD.md)
- [65_COST_GOVERNOR.md](file:///e:/jarvis/docs/65_COST_GOVERNOR.md)
- [73_HEALTH_MONITORING.md](file:///e:/jarvis/docs/73_HEALTH_MONITORING.md)
- [36_EVENT_STANDARD.md](file:///e:/jarvis/docs/36_EVENT_STANDARD.md)
- [87_PHASE_26_MULTI_AGENT_PERSISTENT_RECOVERY_SPECIFICATION.md](file:///e:/jarvis/docs/87_PHASE_26_MULTI_AGENT_PERSISTENT_RECOVERY_SPECIFICATION.md)
- [60_MASTER_INDEX.md](file:///e:/jarvis/docs/60_MASTER_INDEX.md)

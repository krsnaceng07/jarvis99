# 89_PHASE_27_IMPLEMENTATION_PLAN.md

## Phase 27 — Observability, Cost Governance & Live Execution Streaming
## Implementation Plan

**Specification:** `docs/88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md`
**Status:** PROPOSED (Awaiting Architect Approval)
**Dependencies:** Phases 1–26 (all FROZEN)
**Current test baseline:** 1005 passing tests

---

## Milestone Breakdown

### Milestone 27.A — DTOs, Schemas & Repository Layer
**Goal:** Define all new Pydantic DTOs and SQLAlchemy schemas. Implement `SpanRepository` and `BudgetRepository`. No business logic.

**Files (NEW):**
- `core/observability/__init__.py`
- `core/observability/dto.py` — `TraceSpanRecord`, `BudgetSummary`, `CostDecision`, `TelemetryEnvelope`, `SpanSummary`
- `core/observability/models.py` — SQLAlchemy: `TraceSpanModel`, `BudgetLedgerModel`, `ComponentHealthModel`
- `core/observability/span_repository.py` — `SpanRepository`
- `core/observability/budget_repository.py` — `BudgetRepository`
- `tests/test_observability_repositories.py` — ≥ 8 tests

**Quality Gate:** `mypy`, `ruff`, `pytest tests/test_observability_repositories.py`
**Expected tests added:** +8 (total: ~1013)

---

### Milestone 27.B — ExecutionTracer & CostGovernor
**Goal:** Implement the two core business logic components. Both are standalone services that consume events and call repositories.

**Files (NEW):**
- `core/observability/tracer.py` — `ExecutionTracer`
- `core/observability/cost_governor.py` — `CostGovernor`, pricing config `MODEL_PRICING_USD_PER_1K_TOKENS`
- `tests/test_execution_tracer.py` — ≥ 7 tests
- `tests/test_cost_governor.py` — ≥ 7 tests (all four CostDecision tiers)

**Quality Gate:** `mypy`, `ruff`, `pytest tests/test_execution_tracer.py tests/test_cost_governor.py`
**Expected tests added:** +14 (total: ~1027)

---

### Milestone 27.C — HealthProbe & TelemetryBroadcaster
**Goal:** Implement the health monitoring and WebSocket fan-out components.

**Files (NEW):**
- `core/observability/health_probe.py` — `HealthProbe`
- `core/observability/broadcaster.py` — `TelemetryBroadcaster`
- `tests/test_health_probe.py` — ≥ 5 tests
- `tests/test_telemetry_broadcaster.py` — ≥ 5 tests

**Quality Gate:** `mypy`, `ruff`, `pytest tests/test_health_probe.py tests/test_telemetry_broadcaster.py`
**Expected tests added:** +10 (total: ~1037)

---

### Milestone 27.D — API Routes & Prometheus Endpoint
**Goal:** Expose REST and WebSocket endpoints. Wire components into kernel lifecycle.

**Files (NEW):**
- `core/observability/routes.py` — FastAPI router with 4 REST routes + 1 WebSocket route
- `core/observability/metrics.py` — Prometheus `/metrics` text exposition

**Files (MODIFY — non-frozen):**
- `core/kernel.py` — Register `ObservabilityService` in `LifecycleManager`; mount observability router

**Tests (NEW):**
- `tests/test_observability_routes.py` — ≥ 8 tests (REST + WebSocket)

**Quality Gate:** `mypy`, `ruff`, `pytest tests/test_observability_routes.py`
**Expected tests added:** +8 (total: ~1045)

---

### Milestone 27.E — Integration & Event Bus Wiring
**Goal:** Wire all event bus subscriptions. Add integration test validating end-to-end span creation from event publication.

**Files (NEW):**
- `core/observability/service.py` — `ObservabilityService` (lifecycle wrapper; subscribes all event topics)
- `tests/test_observability_integration.py` — ≥ 5 integration tests

**Quality Gate (FINAL):** Full suite — `ruff format --check`, `ruff check`, `mypy`, `pytest` (all 1050+ tests), coverage ≥ 80%
**Expected tests added:** +5 (total: ~1050)

---

## DTO-First Ordering (per AGENTS.md §7.5)

```
dto.py + models.py (M27.A)
        ↓
span_repository.py + budget_repository.py (M27.A)
        ↓
tracer.py + cost_governor.py (M27.B)
        ↓
health_probe.py + broadcaster.py (M27.C)
        ↓
routes.py + metrics.py (M27.D)
        ↓
service.py (M27.E)
        ↓
Tests (each milestone)
```

---

## Frozen Files — NOT TOUCHED

All files in `FREEZE_LEDGER.md`. Specifically:
- `core/reasoning/agent_loop.py` — NOT modified (event publication added only via new service subscriber)
- `core/runtime/orchestrator.py` — NOT modified
- `core/tools/llm_runtime.py` — NOT modified (new `llm.tokens.used` event is published FROM new service; LlmRuntime remains frozen)

---

## Test Target Summary

| Milestone | New Tests | Cumulative |
|-----------|-----------|------------|
| Baseline  | —         | 1005       |
| 27.A      | +8        | ~1013      |
| 27.B      | +14       | ~1027      |
| 27.C      | +10       | ~1037      |
| 27.D      | +8        | ~1045      |
| 27.E      | +5        | ~1050      |

---

## Verification Plan

### Per-Milestone (Mini Gate)
```bash
ruff format --check core/observability/
ruff check core/observability/
mypy core/observability/<new_file>.py
pytest tests/test_<milestone_file>.py -v
```

### Final Gate (M27.E)
```bash
ruff format --check .
ruff check .
mypy core/
pytest --cov=core --cov-report=term-missing
python scripts/quality_gate.py
```

**Regression target:** Zero (1005 existing tests must remain green at every milestone)

---

## Open Questions for Architect

> **Q1 — Event publication from LlmRuntime:**
> `LlmRuntime` is frozen. How should `llm.tokens.used` events be published?
>
> **Option A:** `ObservabilityService` wraps the LLM call via an adapter pattern — but this risks modifying frozen callers.
> **Option B:** `CostGovernor` is called directly from the API layer after each LLM response (not event-driven for token cost, only for tracing) — simpler, no frozen interface change.
> **Option C (Recommended):** `LlmRuntime` already emits `llm.response` events (if the event bus is wired). `CostGovernor` subscribes to those and extracts token counts from the response payload. No frozen file touched.
>
> → **Awaiting Architect decision.**

> **Q2 — Auth on WebSocket endpoint:**
> Phase 17 (Auth) is frozen. Should `/ws/v1/telemetry/stream` require auth tokens or be open (dev mode) by default?
>
> **Recommended:** Open by default (configurable via `JARVIS_TELEMETRY_AUTH_REQUIRED: bool = False`). Enables easy local development without breaking frozen auth interface.
>
> → **Awaiting Architect decision.**

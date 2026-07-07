# PHASE_39_IMPLEMENTATION_PLAN.md

## Status
**STATUS:** ✅ APPROVED
**Authority:** Rank 5 (Implementation Plan)
**Specification:** `docs/101_PHASE_39_WORKFLOW_GRAPH_ENGINE_SPECIFICATION.md`
**Dependencies:** Phase 37 (BrainKernel), Phase 38 (UnifiedMemory)
**Date:** 2026-07-06

---

## 1. Overview

This plan breaks Phase 39 into four milestones, each independently gate-able. No milestone begins until the previous is architect-approved.

---

## 2. File Map

| File | Milestone | Responsibility |
|------|-----------|----------------|
| `core/workflow/workflow_graph.py` | M1 | DAG node/edge data model + cycle validation |
| `core/workflow/dag_scheduler.py` | M1 | Topological sort + parallel wave generator |
| `core/workflow/workflow_engine.py` | M1 | Public façade skeleton + DI wiring |
| `core/workflow/retry_policy.py` | M2 | Configurable backoff + error-classification retry |
| `core/workflow/workflow_executor.py` | M2 | Async step execution with retry integration |
| `core/workflow/checkpoint_store.py` | M3 | Checkpoint persist/load via UnifiedMemory |
| `core/workflow/workflow_template.py` | M3 | ProceduralMemory-backed template registry |
| `core/kernel.py` | M1 | DI registration for all workflow components |
| `api/dependencies.py` | M1 | `get_workflow_engine` provider |
| `tests/test_workflow_graph_engine.py` | M4 | Full verification suite |

---

## 3. Milestones

### Milestone 1 — DAG Core & DI Wiring
**Scope:**
- `core/workflow/workflow_graph.py` — `WorkflowNode`, `WorkflowGraph` with validation + `get_ready_nodes`
- `core/workflow/dag_scheduler.py` — `DAGScheduler` with topological sort yielding parallel waves
- `core/workflow/workflow_engine.py` — public façade skeleton (no execution yet)
- Register all components in `core/kernel.py`
- Expose `get_workflow_engine` in `api/dependencies.py`

**Mini Quality Gate:** `ruff check` + `ruff format --check` + `mypy` on new files only.

---

### Milestone 2 — Executor, Retry, Parallel Dispatch
**Scope:**
- `core/workflow/retry_policy.py` — configurable exponential backoff, max attempts, retryable error list
- `core/workflow/workflow_executor.py` — async executor driving DAG waves, calling retry policy

**Mini Quality Gate:** same files only.

---

### Milestone 3 — Checkpoint/Resume & Templates
**Scope:**
- `core/workflow/checkpoint_store.py` — save/load workflow state via `UnifiedMemory.working_memory`
- `core/workflow/workflow_template.py` — register/instantiate templates via `ProceduralMemory`
- Wire checkpoint and template into `WorkflowEngine`

**Mini Quality Gate:** same files only.

---

### Milestone 4 — Verification & Final Quality Gate
**Scope:**
- `tests/test_workflow_graph_engine.py` — comprehensive test suite covering:
  - Cycle detection rejection
  - Root node resolution
  - Topological wave ordering
  - Parallel wave execution
  - Retry with backoff
  - Checkpoint save/load/resume
  - Template register and instantiate
  - Full WorkflowEngine `run()` and `resume()` flows
- Run full `pytest` suite; confirm **zero regressions**; confirm **≥80% coverage** maintained.

**Final Quality Gate:** `ruff format --check` + `ruff check` + `mypy` (all files) + `pytest` (full suite).

---

## 4. Architecture Constraints (non-negotiable)

1. `core/workflow/` components import only from `core/memory/`, `core/runtime/`, and standard library.
2. No `api/` import inside `core/workflow/`.
3. `WorkflowEngine` is the only class exposed outside `core/workflow/`.
4. Retry logic never modifies graph state — it only retries the callable.
5. CheckpointStore writes only through `UnifiedMemory`, not directly to any DB.

---

## 5. Verification Plan

### Automated
```
pytest tests/test_workflow_graph_engine.py -v
pytest  # full suite, zero regression
```

### Manual
None required — all behavior is unit-testable.

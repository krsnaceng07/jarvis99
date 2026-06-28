# 75_PHASE_13_MASTER_SPECIFICATION.md

## Purpose
This document establishes the Frozen Architecture Specification for **Phase 13: Tool Ecosystem & Workflow Automation**. It serves as the authoritative reference for the workflow automation layer added on top of the frozen Phase 9–12 baseline. Any modification to these components requires a formal Change Request (CR).

## Status
**STATUS: FROZEN — Phase 13 Approved & Baseline Locked**
Approved by Architecture Gatekeeper after full quality gate verification.
Freeze Date: 2026-06-28

---

## Phase 13 System Baseline

### Architecture Boundary

```
WorkflowPlan (Input)
      │
      ▼
WorkflowValidator         ← schema, tool registry, cycle detection
      │
      ▼
WorkflowCompiler          ← topological wave ordering, variable binding checks
      │
      ▼
CompiledWorkflow          ← immutable (frozen=True), deterministic graph
      │
      ▼
WorkflowOrchestrator      ← state transitions, parallel waves, recovery policies
      │
      ▼
ExecutionOrchestrator     ← existing Phase 11 engine (frozen, unchanged)

Persistence (separate path):
WorkflowPlan → WorkflowRepository → workflows / workflow_versions (SQLAlchemy)
```

---

## Core DTOs & Enums

### `WorkflowState` (global workflow lifecycle)
| State | Description |
|---|---|
| `PENDING` | Workflow registered, not yet started |
| `VALIDATING` | Schema and tool validation in progress |
| `READY` | Compiled and ready to execute |
| `RUNNING` | Wave execution active |
| `WAITING_APPROVAL` | Paused for human gatekeeper clearance |
| `PAUSED` | Manually suspended |
| `FAILED` | Execution failed with no recovery |
| `COMPLETED` | All steps succeeded |
| `CANCELLED` | Terminated by user or timeout |

### `WorkflowStepState` (per-step lifecycle)
| State | Description |
|---|---|
| `PENDING` | Not yet started |
| `RUNNING` | Executing via `ExecutionOrchestrator` |
| `WAITING_APPROVAL` | Blocked on L2/L3 approval gate |
| `COMPLETED` | Step returned successfully |
| `FAILED` | Step raised an error |
| `CANCELLED` | Skipped or aborted |

### `RecoveryPolicy` (per-step failure recovery)
| Policy | Behaviour |
|---|---|
| `STOP` | Halt workflow immediately on step failure |
| `CONTINUE` | Log failure and proceed to next wave |
| `RETRY_STEP` | Retry the failed step (max 3 attempts, 2s backoff) |
| `RETRY_WORKFLOW` | Reserved: restart full workflow |
| `ROLLBACK` | Reserved: inverse compensation steps |
| `COMPENSATE` | Reserved: saga-style compensating transactions |

---

## Component Responsibilities

### `WorkflowValidator` — [`core/tools/validator.py`](file:///e:/jarvis/core/tools/validator.py)
- Schema bounds validation (step count ≤ 100, timeout 1–86400s)
- Duplicate step name detection
- Tool registry existence check
- `jarvis_version` compatibility check
- DAG dependency existence validation
- Topological cycle detection (DFS)
- Variable reference syntax validation (`{{steps.X.output.Y}}`)

### `WorkflowCompiler` — [`core/tools/compiler.py`](file:///e:/jarvis/core/tools/compiler.py)
- Kahn's Algorithm topological sort → wave partition generation
- Reference existence validation (all referenced steps declared)
- Circular variable reference detection
- Nesting depth limit (max 3 levels)
- Returns immutable `CompiledWorkflow(frozen=True)`

### `WorkflowRepository` — [`core/tools/repository.py`](file:///e:/jarvis/core/tools/repository.py)
- `WorkflowModel` ORM: active workflow configurations
- `WorkflowVersionModel` ORM: per-version history records
- SHA-256 checksum deduplication (no duplicate version on unchanged content)
- Automatic version increment on definition change
- Soft delete (`is_deleted`) for audit trail preservation
- **No business logic, validation, or compilation** — pure persistence

### `WorkflowOrchestrator` — [`core/tools/workflow_orchestrator.py`](file:///e:/jarvis/core/tools/workflow_orchestrator.py)
- Wave-by-wave concurrent execution via `asyncio.gather`
- Variable template binding at runtime (`{{steps.X.output.Y}}`) — str, dict, list supported
- `RecoveryPolicy` enforcement (STOP / RETRY_STEP / CONTINUE)
- `WorkflowMetrics` accumulation: `Decimal` cost, duration, success_rate, retry_count
- EventBus lifecycle events: `workflow.started` → step-level events → `workflow.completed/failed`
- Delegates all step execution to `ExecutionOrchestrator.execute_task_step()` — does **not** bypass Phase 11

### `SkillManifest` extension — [`core/tools/base.py`](file:///e:/jarvis/core/tools/base.py)
Two fields added (additive, backward-compatible):
- `jarvis_version: str` — minimum compatible JARVIS OS platform version (default `"1.0"`)
- `capabilities: List[str]` — declarative capability tags (e.g. `file_io`, `web_search`, `code_exec`)

---

## DI Container Registration — [`core/kernel.py`](file:///e:/jarvis/core/kernel.py)

All four services registered as singletons during `Kernel.boot()`:

```python
WorkflowValidator(registry=registry)
WorkflowCompiler()
WorkflowRepository()
WorkflowOrchestrator(orchestrator=orchestrator, event_bus=event_bus)
```

---

## Variable Resolution Specification

Template format: `{{steps.<step_name>.output.<variable_name>}}`

Resolution rules:
1. If string is exactly one template → resolve to native type (dict, list, int, etc.)
2. If string contains multiple templates → string substitution (all resolved to `str`)
3. Missing step in `step_outputs` → `ValueError("Step '...' has not executed yet.")`
4. Missing variable key → `ValueError("Variable '...' missing from step '...' outputs.")`
5. Dict/List arguments → recursively resolved before step execution

---

## Architecture Invariants (must never be violated by CR)

| Invariant | Enforcement |
|---|---|
| `CompiledWorkflow` is immutable | `model_config = {"frozen": True}` |
| Compiler always receives `WorkflowPlan` (not DB-loaded object) | By design — Repository returns `WorkflowPlan` model |
| Repository contains no validation or compilation logic | Enforced by SRP + 100% test coverage |
| `WorkflowOrchestrator` delegates to `ExecutionOrchestrator` | Import boundary — no direct `ToolRuntime` calls |
| Frozen Phase 9–12 files unchanged | Verified: 187/187 tests pass |

---

## Quality Gate Results (Freeze Verified)

| Gate | Result |
|---|---|
| Ruff Format | ✅ Passed |
| Ruff Lint | ✅ All checks passed |
| Mypy | ✅ No issues (7 Phase 13 source files) |
| Phase 13 Tests | ✅ 5/5 passed |
| `workflow_dto.py` coverage | ✅ 100% |
| `validator.py` coverage | ✅ 100% |
| `compiler.py` coverage | ✅ 100% |
| `repository.py` coverage | ✅ 100% |
| `workflow_orchestrator.py` coverage | ✅ 100% |
| Full suite regression | ✅ **187 passed, 0 failed** |

---

## Future Change Control Process (CR)

To modify any Phase 13 component, a formal Change Request must be proposed:
1. **Change Proposal:** Declare name `CR-XXX`, reasoning, files affected, risks, and benefits.
2. **Review:** Architecture Gatekeeper reviews for SRP, immutability, and frozen Phase 9–12 boundary compliance.
3. **Approval:** Freeze lock updated only after explicit human Gatekeeper approval.

---

## Related Documents
- [60_MASTER_INDEX.md](file:///e:/jarvis/docs/60_MASTER_INDEX.md)
- [74_PHASE_1_12_MASTER_SPECIFICATION.md](file:///e:/jarvis/docs/74_PHASE_1_12_MASTER_SPECIFICATION.md)
- [57_IMPLEMENTATION_ROADMAP.md](file:///e:/jarvis/docs/57_IMPLEMENTATION_ROADMAP.md)
- [17_SKILL_SDK_SPEC.md](file:///e:/jarvis/docs/17_SKILL_SDK_SPEC.md)

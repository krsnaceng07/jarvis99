# JARVIS OS — Architecture Freeze Document

**Date:** 2026-07-08  
**Status:** FROZEN — no new features until production gate passes  
**Baseline:** 1600+ tests green, mypy clean, ruff clean, kernel boots clean

---

## 1. System Overview

JARVIS OS is an autonomous AI agent system built in async Python (>=3.11, Pydantic v2).
The architecture follows a layered design: Kernel → Runtime → Reasoning → Memory → Tools → Events.

```
User Goal
  │
  ▼
BrainKernel.step()  ←── OUR-PDE-RL cognitive loop
  │
  ▼
MissionManager  ←── goal decomposition, lifecycle, budget gates
  │
  ├──► ParallelMissionPlanner  ←── wave-based parallelism
  ├──► AgentRoleAssigner       ←── RESEARCH/CODING/TESTING/etc.
  ├──► AgentSupervisor         ←── wave completion tracking
  ├──► DeadlockDetector        ←── DFS cycle detection
  │
  ▼
SwarmOrchestrator.spawn_task()
  │
  ▼
ToolDispatcher.dispatch()
  │
  ├──► Executor (Python/Shell/LLM/API)
  ├──► RepairEngine (on failure)
  │      └── Classify → Diagnose → Plan → Retry → Learn → Update
  │
  ▼
ResultMerger + ConflictResolver  ←── aggregate parallel outputs
  │
  ▼
MemoryOrchestrator  ←── store/recall/reflect/forget
  │
  ▼
Mission Complete / Next Wave
```

## 2. Boot Sequence (Kernel.boot)

The kernel boots ~37 phases sequentially via DI container:

| Phase | Component | File |
|-------|-----------|------|
| 1-3 | Vault, EventBus, Settings | core/kernel.py |
| 4-8 | ToolRegistry, Sandbox, PermissionGatekeeper, WaveExecutor, ExecutionOrchestrator | core/tools/ |
| 9-12 | ModelRouter, PlanningService, ToolSelectionEngine, ReasoningExecutionEngine | core/reasoning/ |
| 13 | Workflow Engine | core/runtime/ |
| 15 | Persistence (DB) | core/memory/database.py |
| 17 | Security | core/security/ |
| 19 | MemoryOrchestrator (initial) | core/memory/orchestrator.py |
| 26 | SwarmTaskQueue, AgentRegistry, RepairEngine, ToolDispatcher → SwarmOrchestrator | core/reasoning/ + core/runtime/ |
| 27 | Observability | core/observability/ |
| 30-33 | Cloud, Federation, Admin, Deployment | core/cloud/ etc. |
| 34 | **MissionManager** (with Goal #5 components) | core/runtime/mission.py |
| 37 | **BrainKernel** | core/runtime/brain_kernel.py |
| 38 | Unified Memory, Knowledge Graph | core/memory/ |
| Final | MemoryOrchestrator wired into BrainKernel + MissionManager (lazy) | core/kernel.py |

## 3. Core Components

### 3.1 BrainKernel (`core/runtime/brain_kernel.py`)

High-level cognitive orchestrator. `step()` runs: Observe → Understand → Reason → Plan → Decide → Execute → Reflect → Learn (OUR-PDE-RL loop). Brackets with THICK_CYCLE_START/END events. Holds references to MissionManager and MemoryOrchestrator.

### 3.2 MissionManager (`core/runtime/mission.py`)

Mission lifecycle manager. Dependencies:

- settings, db_manager, event_bus, vault_manager
- orchestrator (SwarmOrchestrator)
- planner (LLM-based goal decomposition)
- parallel_planner (ParallelMissionPlanner)
- role_assigner (AgentRoleAssigner)
- result_merger (ResultMerger)
- conflict_resolver (ConflictResolver)
- supervisor (AgentSupervisor)
- memory_orchestrator (MemoryOrchestrator)

Public API: `create_mission`, `start_mission`, `pause_mission`, `resume_mission`, `cancel_mission`, `create_checkpoint`, `rollback_to_checkpoint`, `append_timeline_event`.

Execution flow:
1. `start_mission()` → recall memory → decompose goal → route to parallel or sequential path
2. Parallel path: plan waves → assign roles → register with supervisor → spawn tasks → resolve conflicts → merge results → complete
3. Sequential path (fallback): execute steps one-by-one with budget gates

### 3.3 SwarmOrchestrator (`core/runtime/orchestrator.py`)

Task execution engine. `spawn_task()` acquires lock → negotiates capability → enqueues → publishes TASK_ASSIGNED event. Supports pause/resume/cancel per task.

### 3.4 ToolDispatcher (`core/reasoning/dispatcher.py`)

Dispatch flow: lookup executor → execute → record metrics → on failure, invoke RepairEngine.attempt_repair (preferred) or _retry_with_fallback (max 2 retries).

### 3.5 RepairEngine (`core/reasoning/repair_engine.py`)

6-stage autonomous repair pipeline:
1. **Classify** — ReflectionEngine categorizes the failure
2. **Diagnose** — reuse cached diagnosis or LLM call for unknowns
3. **Plan** — rank ≤3 repair strategies (cache/reflection/fallback/LLM)
4. **Retry** — execute strategies in ranked order
5. **Learn** — store RepairRecord, cache winning strategy
6. **Update** — expose repair history/success rate/category stats

### 3.6 Multi-Agent Components (Goal #5)

| Component | File | Responsibility |
|-----------|------|---------------|
| ParallelMissionPlanner | core/runtime/parallel_planner.py | Convert sequential steps → ExecutionWaves |
| AgentRoleAssigner | core/runtime/role_assigner.py | Assign RESEARCH/CODING/TESTING/REVIEW/DOCUMENTATION/COORDINATION roles |
| ResultMerger | core/runtime/result_merger.py | Aggregate AgentOutputs per wave and per mission |
| ConflictResolver | core/runtime/conflict_resolver.py | Detect technology/approach conflicts between agents |
| AgentSupervisor | core/runtime/supervisor.py | Track wave completion, detect stalls, abort on mass failure |
| DeadlockDetector | core/runtime/deadlock_detector.py | DFS cycle detection in wait-for graphs |

### 3.7 MemoryOrchestrator (`core/memory/orchestrator.py`)

Dependencies: memory_service, scoring_engine, retention_engine, retrieval_engine, intelligence_service, memory_repo, event_bus, vector_index.

API: `store`, `recall(RetrievalRequest) → RetrievalResponse`, `reflect`, `forget`, `archive`, `promote`, `score`, `run_retention_cycle`.

Feeds both BrainKernel (in step loop) and MissionManager (before planning).

### 3.8 LlmRuntime (`core/tools/llm_runtime.py`)

Budget-gated, provider-agnostic LLM interface. Requires IModelProvider (generate/stream_generate) and CostGovernor. Request/response via LlmRequest/LlmResponse DTOs.

## 4. Key Data Types

| DTO | Module | Fields |
|-----|--------|--------|
| RetrievalRequest | core/memory/dto.py | query, max_chunks, max_tokens, min_score |
| RetrievalResponse | core/memory/dto.py | chunks, scores |
| Task | core/reasoning/task.py | id, goal_id, executor (ExecutorType), task_type (TaskType) |
| ToolExecutionResult | core/tools/dto.py | task_id, status, stdout, stderr |
| LlmRequest | core/tools/llm_runtime.py | prompt, system_prompt, category, max_tokens, temperature |
| AgentOutput | core/runtime/result_merger.py | agent_id, role, stdout, status |
| MergedResult | core/runtime/result_merger.py | success, combined_output, conflicts |
| WaveStep | core/runtime/parallel_planner.py | step_index, description, executor |
| ExecutionWave | core/runtime/parallel_planner.py | wave_index, steps |
| RoleAssignment | core/runtime/role_assigner.py | agent_id, role, task_description, wave_index, confidence |
| RepairOutcome | core/reasoning/repair_engine.py | success, strategy_used, attempts, final_result |

## 5. NOT Duplicates (Architecture Decision)

These pairs are intentionally separate:

1. **MissionManager._decompose_goal** vs **TaskGenerator** — different abstraction levels (mission steps vs reasoning tasks)
2. **core/reasoning/reflection.py** (ReflectionEngine) vs **core/runtime/neural/reflection_engine.py** — pattern-based failure classification vs LLM-based execution analysis

## 6. Directory Structure

```
core/
├── runtime/     (39 files) — mission, orchestrator, brain_kernel, supervisor, role_assigner,
│                              result_merger, conflict_resolver, deadlock_detector, parallel_planner
├── reasoning/   (34 files) — dispatcher, repair_engine, planning_service, tool_selector, reflection
├── memory/      (36 files) — orchestrator, knowledge_graph, working/long_term/episodic/semantic/procedural
├── tools/       (28 files) — registry, llm_runtime, wave_executor, sandbox
├── events/      (6 files)  — memory_bus, reactive_router, redis_bus, schemas
└── config.py, kernel.py
```

## 7. Test Coverage

| Suite | File | Tests | Scope |
|-------|------|-------|-------|
| E2E Integration | tests/test_e2e_integration.py | ~20 | Full mission flow, component wiring, repair, memory recall |
| Production Gate | tests/test_production_gate.py | 21 | Stress (3), Chaos (6), Long-running (4), Performance (8) |
| Existing | tests/ | 1600+ | Unit + integration across all modules |

## 8. Production Gate Checklist

| # | Item | Status |
|---|------|--------|
| 1 | Real E2E Test (LLM-backed runtime) | DONE |
| 2 | Stress Test (20+ parallel missions) | DONE |
| 3 | Chaos Test (failure injection) | DONE |
| 4 | Long-running Mission Test (pause/checkpoint/resume) | DONE |
| 5 | Performance Baseline (latency benchmarks) | DONE |
| 6 | Architecture Freeze Document | THIS DOCUMENT |

**Next:** Goal #6 — Long-running Autonomous Missions (only after all tests pass on user's machine).

# PHASE_37_IMPLEMENTATION_PLAN.md

## Purpose
This document establishes the execution roadmap for **Phase 37: Brain Kernel & Neural Intelligence Layer**. It outlines the directory structuring, milestone deliverables, and verification checkpoints to coordinate central intelligence without changing frozen legacy interfaces.

## Status
**STATUS:** DRAFT (Awaiting Approval)
**Authority:** Rank 5 (Implementation Plan)
**Dependencies:** Phase 36

---

## 1. Planned Changes

| Component | Target File | Responsibility |
| --------- | ----------- | -------------- |
| **Brain Core** | `core/runtime/brain_kernel.py` | Coordinates the thinking loop and delegates goals. |
| | `core/runtime/brain_context.py` | Aggregates global runtime context. |
| | `core/runtime/brain_state.py` | Data structure representing the active cognitive state. |
| | `core/runtime/brain_events.py` | Custom event definitions for event-driven coordination. |
| **Neural Subsystem** | `core/runtime/neural/model_router.py` | Routes LLM tasks across providers. |
| | `core/runtime/neural/reasoning_engine.py` | Encapsulates LLM reasoning loops. |
| | `core/runtime/neural/planning_engine.py` | Encapsulates goal decomposition logic. |
| | `core/runtime/neural/reflection_engine.py` | Encapsulates validation/verification logic. |
| | `core/runtime/neural/learning_engine.py` | Dynamic memory ingestion and ranking coordinator. |
| | `core/runtime/neural/embedding_engine.py` | Embeddings query generator wrapper. |
| **Policy** | `core/runtime/policy/decision_engine.py` | Decision-permission gatekeeper interceptor. |
| **System Integration** | `core/kernel.py` | Wire `BrainKernel` into container boot registry. |
| | `api/dependencies.py` | Expose `get_brain_kernel` dependency injection hook. |
| **Verification** | `tests/test_brain_kernel.py` | Verification checking thinking cycles and state updates. |

---

## 2. Milestones and Quality Gates

### Milestone 1: Brain Core Skeleton
* Create `brain_kernel.py`, `brain_context.py`, `brain_state.py`, and `brain_events.py`.
* Register services inside `core/kernel.py` and `api/dependencies.py`.
* **Mini Quality Gate**: `ruff check`, `mypy --strict` on added files.

### Milestone 2: Neural Subsystem
* Create `neural/model_router.py`, `neural/reasoning_engine.py`, `neural/planning_engine.py`, and `neural/embedding_engine.py`.
* Implement interface wrappers routing queries through the unified Model Router.
* **Mini Quality Gate**: `ruff check`, `mypy --strict` on added files.

### Milestone 3: Decision Policy & Events
* Create `policy/decision_engine.py`.
* Wire decisions with `EventBus` to support decoupled agent-to-agent notification signals.
* **Mini Quality Gate**: `ruff check`, `mypy --strict` on added files.

### Milestone 4: Reflection & Learning
* Create `neural/reflection_engine.py` and `neural/learning_engine.py`.
* Wire with memory updates.
* **Mini Quality Gate**: `ruff check`, `mypy --strict` on added files.

### Milestone 5: Full Integration & Freeze
* Hook Brain Kernel with existing Mission Engine, Federation, Scale, and Consensus.
* Execute full test suite `tests/test_brain_kernel.py`.
* **Final Quality Gate**: `python scripts/quality_gate.py` passes cleanly.

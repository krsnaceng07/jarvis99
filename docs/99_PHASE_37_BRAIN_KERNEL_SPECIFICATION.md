# 99_PHASE_37_BRAIN_KERNEL_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 37: Brain Kernel & Neural Intelligence Layer**. It defines a central cognitive core (the Brain Kernel) to coordinate agent identities, personality states, attention queues, model routing, reasoning, reflection, and policy execution under an event-driven model.

## Status
**STATUS:** ✅ FROZEN (2026-07-05)
**Test Count:** 1136 passed tests
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 36

---

## 1. Architectural Position

The Brain Kernel becomes the unified coordinator of JARVIS OS, intercepting all user goals and orchestrating downstream managers (e.g. mission, scale, tools) via a neural translation layer:

```
                  User Goal
                      │
                      ▼
             [ Brain Kernel ]  <─── Event Bus (GoalCreated)
                      │
      ┌───────────────┴───────────────┐
      ▼                               ▼
[ Neural Layer ]              [ Cognitive State ]
(Model Router, Reasoning)     (Attention, Energy, Confidence)
      │
      ▼
[ Policy/Decision ]
(Permissions & Checks)
      │
      ▼
[ Workflow / Mission ]
(Subprocess executions)
```

---

## 2. Directory Layout & Structure

All modules added in Phase 37 must reside in additive namespaces:

```text
core/runtime/
  ├── brain_kernel.py       # BrainKernel loop coordinator
  ├── brain_context.py      # Global context management
  ├── brain_state.py        # CognitiveState data definitions
  ├── brain_events.py       # Goal/Execution domain events
  ├── neural/
  │    ├── model_router.py      # Unified LLM provider route selector
  │    ├── reasoning_engine.py  # Abstracted LLM reasoning wrapper
  │    ├── planning_engine.py   # System-wide goal decomposer
  │    ├── reflection_engine.py # Step-by-step validator & corrector
  │    ├── learning_engine.py   # Memory indexing corrector
  │    └── embedding_engine.py  # pgvector embedding helper
  └── policy/
       └── decision_engine.py   # Action permission scanner
```

---

## 3. Component Contracts

### 3.1 BrainKernel

```python
class BrainKernel:
    """The central orchestrator of cognitive states and thinking loops."""

    def __init__(
        self,
        settings: Any,
        state: CognitiveState,
        neural_layer: NeuralLayer,
        policy_engine: PolicyEngine,
        event_bus: Any,
    ) -> None:
        """Initialize the Brain Kernel."""

    async def observe(self, observation: Dict[str, Any]) -> None:
        """Process inbound observations and append to attention queue."""

    async def reason(self) -> Dict[str, Any]:
        """Run thinking loops over the active goal stack and state context."""

    async def step(self) -> None:
        """Execute one cycle of the Observe-Understand-Reason-Plan-Execute loop."""
```

### 3.2 CognitiveState

Tracks system attention, energy levels, confidence factors, risk thresholds, and budgets:

```python
class CognitiveState(BaseModel):
    current_goal: Optional[str] = None
    current_mission_id: Optional[UUID] = None
    attention_queue: List[str] = Field(default_factory=list)
    energy: float = 1.0  # Range: [0.0, 1.0]
    confidence: float = 1.0  # Range: [0.0, 1.0]
    risk_level: float = 0.0  # Range: [0.0, 1.0]
    available_budget: float = 0.0
```

---

## 4. Verification and Acceptance Criteria
- **Decoupled Orchestration**: Verify managers no longer invoke each other directly; execution must route strictly via the `BrainKernel` or events.
- **Thinking Loop Validation**: Verify `BrainKernel.step()` runs through the full cycle (Observe → Reason → Plan → Execute → Reflect) successfully.
- **Unified Model Routing**: Verify LLM queries route through `model_router.py` rather than directly to Claude or Llama providers.

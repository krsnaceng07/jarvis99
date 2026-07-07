# 101_PHASE_39_WORKFLOW_GRAPH_ENGINE_SPECIFICATION.md

## Status
**STATUS:** ✅ FROZEN (2026-07-06)
**Test Count:** 1208 passed tests
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 37 (Brain Kernel), Phase 38 (Unified Memory)
**Date:** 2026-07-06

---

## 1. Problem Statement

JARVIS currently executes tasks imperatively — one step at a time through the BrainKernel cognitive loop. There is no native capability to:

- Express multi-step task dependencies as a graph
- Execute parallel branches where order does not matter
- Retry a failed step without restarting the whole mission
- Checkpoint mid-workflow and resume after failure
- Build reusable workflow templates from ProceduralMemory

Phase 39 introduces a **Workflow Graph Engine** that operates as the autonomous execution backbone connecting BrainKernel, MissionManager, Unified Memory, KnowledgeGraph, ScaleManager, and ConsensusManager.

---

## 2. Architectural Position

```
                     BrainKernel
                          │
                          ▼
                  WorkflowGraphEngine
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
  DAGScheduler      RetryPolicy       CheckpointStore
        │                                   │
        ▼                                   ▼
 ParallelExecutor                     UnifiedMemory
        │
        ▼
 MissionManager / ScaleManager / ConsensusManager
```

**Dependency direction:** `WorkflowGraphEngine → {BrainKernel, UnifiedMemory, MissionManager}`. Never the reverse.

---

## 3. Directory Layout

```text
core/workflow/
  ├── workflow_graph.py        # DAG node/edge data model + validation
  ├── dag_scheduler.py         # Topological sort + parallel-branch resolver
  ├── workflow_executor.py     # Async step executor coordinating dependencies
  ├── retry_policy.py          # Configurable backoff, max attempts, error classification
  ├── checkpoint_store.py      # Persist/resume workflow state via UnifiedMemory
  ├── workflow_template.py     # Named reusable workflow patterns
  └── workflow_engine.py       # Public façade wiring all sub-components
```

---

## 4. Component Contracts

### 4.1 WorkflowGraph — DAG Data Model

```python
class WorkflowNode:
    node_id: str
    name: str
    task_type: str          # "tool" | "mission" | "skill" | "llm" | "condition"
    parameters: Dict[str, Any]
    depends_on: List[str]   # upstream node_ids (DAG edges)

class WorkflowGraph:
    graph_id: str
    name: str
    nodes: Dict[str, WorkflowNode]
    metadata: Dict[str, Any]

    def validate(self) -> bool:
        """Assert no cycles; all dependency references exist."""

    def get_roots(self) -> List[WorkflowNode]:
        """Return nodes with no dependencies (execution entry points)."""

    def get_ready_nodes(self, completed: Set[str]) -> List[WorkflowNode]:
        """Return nodes whose all dependencies are satisfied."""
```

### 4.2 DAGScheduler — Topological Resolver

```python
class DAGScheduler:
    async def schedule(self, graph: WorkflowGraph) -> AsyncIterator[List[WorkflowNode]]:
        """Yield waves of nodes that can run in parallel."""
```

### 4.3 WorkflowExecutor — Async Step Executor

```python
class WorkflowExecutor:
    async def execute(self, graph: WorkflowGraph) -> WorkflowResult:
        """Drive the DAG from roots to completion, respecting dependencies."""
```

### 4.4 RetryPolicy — Configurable Failure Handling

```python
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: float = 1.0
    retryable_errors: List[str]

    async def execute_with_retry(self, fn: Callable) -> Any:
        """Run fn with exponential backoff up to max_attempts."""
```

### 4.5 CheckpointStore — Mid-Workflow Persistence

```python
class CheckpointStore:
    async def save(self, graph_id: str, state: Dict[str, Any]) -> None:
        """Persist completed node set and partial results to UnifiedMemory."""

    async def load(self, graph_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve saved checkpoint for a workflow."""
```

### 4.6 WorkflowTemplate — Reusable Patterns

```python
class WorkflowTemplate:
    async def register(self, name: str, graph: WorkflowGraph) -> None:
        """Store a named workflow template in ProceduralMemory."""

    async def instantiate(self, name: str, parameters: Dict[str, Any]) -> WorkflowGraph:
        """Create a runtime graph from a registered template."""
```

### 4.7 WorkflowEngine — Public Façade

```python
class WorkflowEngine:
    async def run(self, graph: WorkflowGraph) -> WorkflowResult:
        """Execute a workflow from scratch."""

    async def resume(self, graph_id: str) -> WorkflowResult:
        """Restore from checkpoint and continue execution."""

    async def register_template(self, name: str, graph: WorkflowGraph) -> None:
        """Store a reusable workflow template."""
```

---

## 5. Key Invariants

| # | Invariant |
|---|-----------|
| W-1 | WorkflowGraph must be a valid DAG (no cycles). Validation runs before execution starts. |
| W-2 | DAGScheduler never executes a node before all its `depends_on` are complete. |
| W-3 | RetryPolicy handles only execution failures. It never mutates the graph. |
| W-4 | CheckpointStore writes only to UnifiedMemory — never directly to the database. |
| W-5 | WorkflowEngine is the only public entry point. Internal components are not exposed to the API layer. |
| W-6 | WorkflowTemplate reads/writes via ProceduralMemory only — never duplicates storage logic. |

---

## 6. Integration Points

| System | Integration |
|--------|-------------|
| BrainKernel | Invokes WorkflowEngine to execute multi-step cognitive plans |
| MissionManager | Workflow steps may dispatch missions as task nodes |
| UnifiedMemory | CheckpointStore persists state; SemanticMemory stores results |
| ProceduralMemory | WorkflowTemplate reads/writes named workflow patterns |
| KnowledgeGraph | Workflow outputs may create entity/relation facts |
| ScaleManager | Parallel branches may be dispatched to remote workers |
| ConsensusManager | Workflow approval gates may require multi-node consensus vote |

---

## 7. Verification & Acceptance Criteria

- **Cycle detection:** A graph with a cycle must be rejected before execution.
- **Parallel execution:** Two nodes with no shared dependency must execute concurrently.
- **Retry:** A failing step retries up to `max_attempts` before the workflow fails.
- **Checkpoint/Resume:** Interrupting a mid-workflow execution and calling `resume()` must continue from the saved state.
- **Template:** A registered template can be instantiated with different parameters.
- **Zero regression:** Full test suite passes with no existing tests broken.

---

## 8. Open Questions

> None currently outstanding. Architecture is fully defined.

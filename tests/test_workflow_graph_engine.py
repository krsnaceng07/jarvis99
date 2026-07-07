"""
PHASE: 39
STATUS: IMPLEMENTATION — Tests
SPECIFICATION:
    docs/101_PHASE_39_WORKFLOW_GRAPH_ENGINE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/PHASE_39_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import pytest

from core.memory.procedural_memory import ProceduralMemory
from core.memory.working_memory import WorkingMemory
from core.workflow.checkpoint_store import CheckpointStore
from core.workflow.dag_scheduler import DAGScheduler
from core.workflow.retry_policy import RetryPolicy
from core.workflow.workflow_engine import WorkflowEngine
from core.workflow.workflow_executor import WorkflowExecutor
from core.workflow.workflow_graph import WorkflowGraph, WorkflowNode
from core.workflow.workflow_template import WorkflowTemplate

# ─────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────


def _node(node_id: str, depends_on: list[str] | None = None) -> WorkflowNode:
    return WorkflowNode(
        node_id=node_id,
        name=f"Task {node_id}",
        task_type="tool",
        parameters={},
        depends_on=depends_on or [],
    )


def _linear_graph(graph_id: str = "g1") -> WorkflowGraph:
    """A → B → C (linear chain)."""
    g = WorkflowGraph(graph_id=graph_id, name="linear")
    g.add_node(_node("A"))
    g.add_node(_node("B", depends_on=["A"]))
    g.add_node(_node("C", depends_on=["B"]))
    return g


def _parallel_graph(graph_id: str = "g2") -> WorkflowGraph:
    """A → {B, C} → D (parallel branches)."""
    g = WorkflowGraph(graph_id=graph_id, name="parallel")
    g.add_node(_node("A"))
    g.add_node(_node("B", depends_on=["A"]))
    g.add_node(_node("C", depends_on=["A"]))
    g.add_node(_node("D", depends_on=["B", "C"]))
    return g


def _make_engine(
    working_memory: WorkingMemory | None = None,
    procedural_memory: ProceduralMemory | None = None,
) -> WorkflowEngine:
    wm = working_memory or WorkingMemory()
    pm = procedural_memory or ProceduralMemory()
    scheduler = DAGScheduler()
    retry_policy = RetryPolicy(max_attempts=3, backoff_seconds=0.0)
    executor = WorkflowExecutor(scheduler=scheduler, retry_policy=retry_policy)
    checkpoint_store = CheckpointStore(working_memory=wm)
    template_registry = WorkflowTemplate(procedural_memory=pm)
    engine = WorkflowEngine(scheduler=scheduler)
    engine.set_executor(executor)
    engine.set_checkpoint_store(checkpoint_store)
    engine.set_template_registry(template_registry)
    return engine


# ─────────────────────────────────────────────────────────────
# WorkflowGraph — DAG validation
# ─────────────────────────────────────────────────────────────


def test_workflow_graph_valid_linear() -> None:
    g = _linear_graph()
    assert g.validate() is True


def test_workflow_graph_cycle_detection() -> None:
    g = WorkflowGraph(graph_id="cycle", name="cycle")
    g.add_node(_node("X", depends_on=["Y"]))
    g.add_node(_node("Y", depends_on=["X"]))
    with pytest.raises(ValueError, match="Cycle detected"):
        g.validate()


def test_workflow_graph_missing_dependency() -> None:
    g = WorkflowGraph(graph_id="bad-dep", name="bad")
    g.add_node(_node("A", depends_on=["MISSING"]))
    with pytest.raises(ValueError, match="unknown node"):
        g.validate()


def test_workflow_graph_get_roots() -> None:
    g = _parallel_graph()
    roots = g.get_roots()
    assert len(roots) == 1
    assert roots[0].node_id == "A"


def test_workflow_graph_get_ready_nodes_empty_completed() -> None:
    g = _parallel_graph()
    ready = g.get_ready_nodes(completed=set())
    assert [n.node_id for n in ready] == ["A"]


def test_workflow_graph_get_ready_nodes_after_a() -> None:
    g = _parallel_graph()
    ready = g.get_ready_nodes(completed={"A"})
    ids = {n.node_id for n in ready}
    assert ids == {"B", "C"}


def test_workflow_graph_get_ready_nodes_after_a_b_c() -> None:
    g = _parallel_graph()
    ready = g.get_ready_nodes(completed={"A", "B", "C"})
    assert [n.node_id for n in ready] == ["D"]


def test_workflow_graph_completed_nodes_excluded() -> None:
    g = _linear_graph()
    # A and B done — only C should be ready
    ready = g.get_ready_nodes(completed={"A", "B"})
    assert len(ready) == 1
    assert ready[0].node_id == "C"


# ─────────────────────────────────────────────────────────────
# DAGScheduler — topological wave ordering
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dag_scheduler_linear_order() -> None:
    g = _linear_graph()
    scheduler = DAGScheduler()
    waves = []
    async for wave in scheduler.schedule(g):
        waves.append([n.node_id for n in wave])
    assert waves == [["A"], ["B"], ["C"]]


@pytest.mark.asyncio
async def test_dag_scheduler_parallel_waves() -> None:
    g = _parallel_graph()
    scheduler = DAGScheduler()
    waves = []
    async for wave in scheduler.schedule(g):
        waves.append(sorted(n.node_id for n in wave))
    assert waves == [["A"], ["B", "C"], ["D"]]


@pytest.mark.asyncio
async def test_dag_scheduler_deterministic_order() -> None:
    """Equal-priority nodes must sort by node_id for determinism."""
    g = WorkflowGraph(graph_id="det", name="det")
    g.add_node(_node("Z"))
    g.add_node(_node("A"))
    g.add_node(_node("M"))
    scheduler = DAGScheduler()
    waves = []
    async for wave in scheduler.schedule(g):
        waves.append([n.node_id for n in wave])
    # All three roots — should appear in alphabetical order in one wave
    assert waves == [["A", "M", "Z"]]


@pytest.mark.asyncio
async def test_dag_scheduler_single_node() -> None:
    g = WorkflowGraph(graph_id="solo", name="solo")
    g.add_node(_node("X"))
    scheduler = DAGScheduler()
    waves = []
    async for wave in scheduler.schedule(g):
        waves.append([n.node_id for n in wave])
    assert waves == [["X"]]


# ─────────────────────────────────────────────────────────────
# RetryPolicy
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_policy_success_first_attempt() -> None:
    policy = RetryPolicy(max_attempts=3, backoff_seconds=0.0)
    calls = 0

    async def ok() -> str:
        nonlocal calls
        calls += 1
        return "done"

    result = await policy.execute_with_retry(ok)
    assert result == "done"
    assert calls == 1


@pytest.mark.asyncio
async def test_retry_policy_retries_on_failure() -> None:
    policy = RetryPolicy(max_attempts=3, backoff_seconds=0.0)
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("transient")
        return "recovered"

    result = await policy.execute_with_retry(flaky)
    assert result == "recovered"
    assert calls == 3


@pytest.mark.asyncio
async def test_retry_policy_exhausts_all_attempts() -> None:
    policy = RetryPolicy(max_attempts=3, backoff_seconds=0.0)
    calls = 0

    async def always_fails() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("permanent")

    with pytest.raises(ValueError, match="permanent"):
        await policy.execute_with_retry(always_fails)
    assert calls == 3


@pytest.mark.asyncio
async def test_retry_policy_non_retryable_raises_immediately() -> None:
    policy = RetryPolicy(
        max_attempts=5,
        backoff_seconds=0.0,
        retryable_errors=["RuntimeError"],
    )
    calls = 0

    async def type_error() -> None:
        nonlocal calls
        calls += 1
        raise TypeError("not retryable")

    with pytest.raises(TypeError):
        await policy.execute_with_retry(type_error)
    assert calls == 1  # no retry for non-retryable errors


def test_retry_policy_backoff_delay() -> None:
    policy = RetryPolicy(max_attempts=5, backoff_seconds=2.0)
    assert policy.backoff_delay(0) == 2.0
    assert policy.backoff_delay(1) == 4.0
    assert policy.backoff_delay(2) == 8.0


def test_retry_policy_is_retryable_empty_list() -> None:
    policy = RetryPolicy()
    assert policy.is_retryable(ValueError("any")) is True


def test_retry_policy_is_retryable_named_list() -> None:
    policy = RetryPolicy(retryable_errors=["ValueError"])
    assert policy.is_retryable(ValueError("yes")) is True
    assert policy.is_retryable(RuntimeError("no")) is False


# ─────────────────────────────────────────────────────────────
# WorkflowExecutor — parallel execution
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_executor_linear_all_nodes_complete() -> None:
    g = _linear_graph()
    scheduler = DAGScheduler()
    executor = WorkflowExecutor(
        scheduler=scheduler,
        retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
    )
    result = await executor.execute(g)
    assert result.success is True
    assert set(result.completed_nodes) == {"A", "B", "C"}


@pytest.mark.asyncio
async def test_executor_parallel_all_nodes_complete() -> None:
    g = _parallel_graph()
    scheduler = DAGScheduler()
    execution_order: list[str] = []

    async def handler(node: WorkflowNode) -> None:
        execution_order.append(node.node_id)

    executor = WorkflowExecutor(
        scheduler=scheduler,
        retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
    )
    executor.register_handler("tool", handler)
    result = await executor.execute(g)
    assert result.success is True
    assert set(result.completed_nodes) == {"A", "B", "C", "D"}
    # B and C must both appear before D
    assert execution_order.index("A") < execution_order.index("B")
    assert execution_order.index("A") < execution_order.index("C")
    assert execution_order.index("B") < execution_order.index("D")
    assert execution_order.index("C") < execution_order.index("D")


@pytest.mark.asyncio
async def test_executor_no_duplicate_execution() -> None:
    """Each node must be executed exactly once."""
    g = _parallel_graph()
    scheduler = DAGScheduler()
    counts: dict[str, int] = {}

    async def handler(node: WorkflowNode) -> None:
        counts[node.node_id] = counts.get(node.node_id, 0) + 1

    executor = WorkflowExecutor(
        scheduler=scheduler,
        retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
    )
    executor.register_handler("tool", handler)
    await executor.execute(g)
    for node_id, count in counts.items():
        assert count == 1, f"Node '{node_id}' executed {count} times"


@pytest.mark.asyncio
async def test_executor_resume_skips_completed() -> None:
    """Nodes in initial_completed must not be executed again."""
    g = _linear_graph()
    scheduler = DAGScheduler()
    executed: list[str] = []

    async def handler(node: WorkflowNode) -> None:
        executed.append(node.node_id)

    executor = WorkflowExecutor(
        scheduler=scheduler,
        retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
    )
    executor.register_handler("tool", handler)
    # A is already done — resume from B
    result = await executor.execute(g, initial_completed={"A"})
    assert result.success is True
    assert "A" not in executed
    assert "B" in executed
    assert "C" in executed


@pytest.mark.asyncio
async def test_executor_propagates_failure() -> None:
    g = _linear_graph()
    scheduler = DAGScheduler()

    async def failing_handler(node: WorkflowNode) -> None:
        raise RuntimeError("node failed")

    executor = WorkflowExecutor(
        scheduler=scheduler,
        retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
    )
    executor.register_handler("tool", failing_handler)
    result = await executor.execute(g)
    assert result.success is False
    assert result.error is not None


# ─────────────────────────────────────────────────────────────
# CheckpointStore
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checkpoint_store_save_and_load() -> None:
    wm = WorkingMemory()
    store = CheckpointStore(working_memory=wm)
    state = {"completed_nodes": ["A", "B"], "outputs": {"A": 1}}
    await store.save("g1", state)
    loaded = await store.load("g1")
    assert loaded is not None
    assert loaded["completed_nodes"] == ["A", "B"]
    assert loaded["outputs"] == {"A": 1}


@pytest.mark.asyncio
async def test_checkpoint_store_load_missing_returns_none() -> None:
    wm = WorkingMemory()
    store = CheckpointStore(working_memory=wm)
    result = await store.load("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_checkpoint_store_delete() -> None:
    wm = WorkingMemory()
    store = CheckpointStore(working_memory=wm)
    await store.save("g1", {"completed_nodes": ["A"]})
    await store.delete("g1")
    # After delete, loading returns None
    loaded = await store.load("g1")
    assert loaded is None


@pytest.mark.asyncio
async def test_checkpoint_store_overwrites_previous() -> None:
    wm = WorkingMemory()
    store = CheckpointStore(working_memory=wm)
    await store.save("g1", {"completed_nodes": ["A"], "outputs": {}})
    await store.save("g1", {"completed_nodes": ["A", "B"], "outputs": {"B": 2}})
    loaded = await store.load("g1")
    assert loaded is not None
    assert loaded["completed_nodes"] == ["A", "B"]


@pytest.mark.asyncio
async def test_checkpoint_store_isolates_graphs() -> None:
    wm = WorkingMemory()
    store = CheckpointStore(working_memory=wm)
    await store.save("g1", {"completed_nodes": ["A"]})
    await store.save("g2", {"completed_nodes": ["X"]})
    g1 = await store.load("g1")
    g2 = await store.load("g2")
    assert g1 is not None
    assert g2 is not None
    assert g1["completed_nodes"] == ["A"]
    assert g2["completed_nodes"] == ["X"]


# ─────────────────────────────────────────────────────────────
# WorkflowTemplate
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workflow_template_register_and_instantiate() -> None:
    pm = ProceduralMemory()
    tpl = WorkflowTemplate(procedural_memory=pm)
    g = _parallel_graph()
    await tpl.register("my-workflow", g)
    instance = await tpl.instantiate("my-workflow")
    assert instance is not None
    assert set(instance.nodes.keys()) == {"A", "B", "C", "D"}


@pytest.mark.asyncio
async def test_workflow_template_not_found_returns_none() -> None:
    pm = ProceduralMemory()
    tpl = WorkflowTemplate(procedural_memory=pm)
    result = await tpl.instantiate("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_workflow_template_parameter_override() -> None:
    pm = ProceduralMemory()
    tpl = WorkflowTemplate(procedural_memory=pm)
    g = WorkflowGraph(graph_id="t1", name="t1")
    g.add_node(WorkflowNode("N1", "node1", "tool", {"env": "dev"}, []))
    await tpl.register("env-workflow", g)
    instance = await tpl.instantiate("env-workflow", parameters={"env": "prod"})
    assert instance is not None
    assert instance.nodes["N1"].parameters["env"] == "prod"


@pytest.mark.asyncio
async def test_workflow_template_independent_instances() -> None:
    """Two instantiations must produce separate graph objects."""
    pm = ProceduralMemory()
    tpl = WorkflowTemplate(procedural_memory=pm)
    g = _linear_graph()
    await tpl.register("linear", g)
    inst1 = await tpl.instantiate("linear", graph_id="run-1")
    inst2 = await tpl.instantiate("linear", graph_id="run-2")
    assert inst1 is not None
    assert inst2 is not None
    assert inst1.graph_id == "run-1"
    assert inst2.graph_id == "run-2"
    # Modifying one must not affect the other
    inst1.add_node(_node("Extra"))
    assert "Extra" not in inst2.nodes


@pytest.mark.asyncio
async def test_workflow_template_list_templates() -> None:
    pm = ProceduralMemory()
    tpl = WorkflowTemplate(procedural_memory=pm)
    await tpl.register("wf-a", _linear_graph())
    await tpl.register("wf-b", _parallel_graph())
    names = await tpl.list_templates()
    assert "wf-a" in names
    assert "wf-b" in names


# ─────────────────────────────────────────────────────────────
# WorkflowEngine — full lifecycle
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_engine_run_linear_success() -> None:
    engine = _make_engine()
    result = await engine.run(_linear_graph())
    assert result.success is True
    assert set(result.completed_nodes) == {"A", "B", "C"}


@pytest.mark.asyncio
async def test_engine_run_parallel_success() -> None:
    engine = _make_engine()
    result = await engine.run(_parallel_graph())
    assert result.success is True
    assert set(result.completed_nodes) == {"A", "B", "C", "D"}


@pytest.mark.asyncio
async def test_engine_run_saves_checkpoint() -> None:
    wm = WorkingMemory()
    engine = _make_engine(working_memory=wm)
    g = _linear_graph("ck-graph")
    await engine.run(g)
    store = CheckpointStore(working_memory=wm)
    cp = await store.load("ck-graph")
    assert cp is not None
    assert set(cp["completed_nodes"]) == {"A", "B", "C"}


@pytest.mark.asyncio
async def test_engine_resume_deterministic() -> None:
    """Resumed workflow must not re-execute already-completed nodes."""
    wm = WorkingMemory()
    engine = _make_engine(working_memory=wm)
    g = _linear_graph("resume-graph")

    # Manually plant a partial checkpoint (A done)
    store = CheckpointStore(working_memory=wm)
    await store.save("resume-graph", {"completed_nodes": ["A"], "outputs": {}})

    executed: list[str] = []
    # Patch executor's handler to track what runs
    scheduler = DAGScheduler()
    retry = RetryPolicy(max_attempts=1, backoff_seconds=0.0)
    executor = WorkflowExecutor(scheduler=scheduler, retry_policy=retry)

    async def handler(node: WorkflowNode) -> None:
        executed.append(node.node_id)

    executor.register_handler("tool", handler)
    engine.set_executor(executor)

    result = await engine.resume(g)
    assert result.success is True
    assert "A" not in executed  # A was already checkpointed
    assert "B" in executed
    assert "C" in executed


@pytest.mark.asyncio
async def test_engine_resume_no_checkpoint_fails() -> None:
    engine = _make_engine()
    g = _linear_graph("no-cp")
    result = await engine.resume(g)
    assert result.success is False
    assert "No checkpoint" in (result.error or "")


@pytest.mark.asyncio
async def test_engine_resume_no_checkpoint_store_fails() -> None:
    scheduler = DAGScheduler()
    engine = WorkflowEngine(scheduler=scheduler)
    g = _linear_graph("no-store")
    result = await engine.resume(g)
    assert result.success is False
    assert "CheckpointStore not configured" in (result.error or "")


@pytest.mark.asyncio
async def test_engine_register_template_and_run() -> None:
    pm = ProceduralMemory()
    engine = _make_engine(procedural_memory=pm)
    g = _parallel_graph("tpl-src")
    await engine.register_template("my-tpl", g)

    # Instantiate the template directly and run it
    tpl = WorkflowTemplate(procedural_memory=pm)
    instance = await tpl.instantiate("my-tpl", graph_id="tpl-run")
    assert instance is not None
    result = await engine.run(instance)
    assert result.success is True
    assert set(result.completed_nodes) == {"A", "B", "C", "D"}


def test_engine_status_initial() -> None:
    engine = _make_engine()
    s = engine.status("unknown-graph")
    assert s["graph_id"] == "unknown-graph"
    assert s["cancelled"] is False


def test_engine_cancel() -> None:
    engine = _make_engine()
    engine.cancel("g1")
    s = engine.status("g1")
    assert s["cancelled"] is True


@pytest.mark.asyncio
async def test_engine_cycle_rejected_before_execution() -> None:
    engine = _make_engine()
    g = WorkflowGraph(graph_id="cyclic", name="cyclic")
    g.add_node(_node("X", depends_on=["Y"]))
    g.add_node(_node("Y", depends_on=["X"]))
    with pytest.raises(ValueError, match="Cycle detected"):
        await engine.run(g)

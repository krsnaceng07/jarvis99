"""JARVIS OS - Workflow Automation Unit & Integration Tests.

Validates DTO contracts, validation routines, compiler rules, repository operations, and workflow orchestrators.
"""

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from core.config import Settings
from core.exceptions import JarvisSkillError
from core.interfaces import EventBusInterface
from core.memory.database import db_manager
from core.memory.models import Base
from core.reasoning.orchestrator import ExecutionOrchestrator
from core.reasoning.planner import ReasoningSession
from core.tools.base import SkillManifest
from core.tools.compiler import WorkflowCompiler
from core.tools.registry import ToolRegistry
from core.tools.repository import WorkflowRepository
from core.tools.validator import WorkflowValidator
from core.tools.workflow_dto import (
    CompiledWorkflow,
    RecoveryPolicy,
    WorkflowMetrics,
    WorkflowPlan,
    WorkflowState,
    WorkflowStep,
)
from core.tools.workflow_orchestrator import WorkflowOrchestrator


def test_workflow_dto_immutability_and_types() -> None:
    """Verify that CompiledWorkflow is immutable and WorkflowMetrics holds decimal types."""
    workflow_id = uuid4()
    step1 = WorkflowStep(
        name="step_one",
        tool_name="cmd_exec",
        arguments={},
        recovery_policy=RecoveryPolicy.STOP,
    )
    compiled = CompiledWorkflow(
        workflow_id=workflow_id,
        version=1,
        waves=[[step1]],
        estimated_cost=Decimal("0.05"),
    )

    # Immutable check
    with pytest.raises(Exception):
        compiled.version = 2

    # Metrics Decimal cost check
    metrics = WorkflowMetrics(
        total_steps=1,
        completed_steps=1,
        token_cost=Decimal("0.045"),
    )
    assert isinstance(metrics.token_cost, Decimal)
    assert metrics.token_cost == Decimal("0.045")


def test_validator_success_and_failures() -> None:
    """Verify WorkflowValidator captures duplicate steps, cycles, timeouts, missing tools, and syntax errors."""
    mock_registry = ToolRegistry(skills_dir="fake_dir")

    # Mock tool registry dynamic skills lookup
    tool_manifest1 = SkillManifest(
        name="cmd_exec",
        version="1.0.0",
        signature="fake_signature",
        jarvis_api_version="1.0",
        skill_version="1.0.0",
        min_runtime_version="1.0",
        permissions=["cli"],
    )
    tool_manifest2 = SkillManifest(
        name="file_writer",
        version="1.0.0",
        signature="fake_signature",
        jarvis_api_version="1.0",
        skill_version="1.0.0",
        min_runtime_version="1.0",
        permissions=["file_write"],
    )

    mock_registry.skills = {
        "cmd_exec": tool_manifest1,
        "file_writer": tool_manifest2,
    }

    validator = WorkflowValidator(registry=mock_registry)

    # 1. Successful scenario
    step1 = WorkflowStep(
        name="step_a",
        tool_name="cmd_exec",
        arguments={"cmd": "echo 1"},
    )
    step2 = WorkflowStep(
        name="step_b",
        tool_name="file_writer",
        arguments={"path": "out.txt", "content": "{{steps.step_a.output.result}}"},
        dependencies=["step_a"],
    )
    plan_ok = WorkflowPlan(
        name="valid_flow",
        workflow_id=uuid4(),
        steps=[step1, step2],
    )
    validator.validate(plan_ok)

    # 2. Failure: empty workflow name
    plan_no_name = WorkflowPlan(
        name="",
        workflow_id=uuid4(),
        steps=[step1],
    )
    with pytest.raises(ValueError, match="Workflow name cannot be empty"):
        validator.validate(plan_no_name)

    # 3. Failure: empty steps list
    plan_no_steps = WorkflowPlan(
        name="empty_steps",
        workflow_id=uuid4(),
        steps=[],
    )
    with pytest.raises(ValueError, match="Workflow must contain at least one step"):
        validator.validate(plan_no_steps)

    # 4. Failure: step name duplicate detection
    step_dup = WorkflowStep(
        name="step_a",
        tool_name="file_writer",
        arguments={},
    )
    plan_dup = WorkflowPlan(
        name="duplicate_names",
        workflow_id=uuid4(),
        steps=[step1, step_dup],
    )
    with pytest.raises(ValueError, match="Duplicate step name 'step_a'"):
        validator.validate(plan_dup)

    # 5. Failure: negative timeout
    step_neg_timeout = WorkflowStep(
        name="neg_timeout",
        tool_name="cmd_exec",
        timeout=-10.0,
    )
    plan_timeout = WorkflowPlan(
        name="bad_timeout",
        workflow_id=uuid4(),
        steps=[step_neg_timeout],
    )
    with pytest.raises(ValueError, match="must have a positive timeout"):
        validator.validate(plan_timeout)

    # 6. Failure: missing tool registry check
    step_missing_tool = WorkflowStep(
        name="missing_tool",
        tool_name="non_existent",
    )
    plan_missing = WorkflowPlan(
        name="missing_tool_flow",
        workflow_id=uuid4(),
        steps=[step_missing_tool],
    )
    with pytest.raises(
        JarvisSkillError, match="references missing or unregistered tool"
    ):
        validator.validate(plan_missing)

    # 7. Failure: API version compatibility mismatch
    tool_incompatible = SkillManifest(
        name="future_tool",
        version="2.0.0",
        signature="fake",
        jarvis_api_version="9.9",  # Newer than 1.0
        skill_version="1.0.0",
        min_runtime_version="1.0",
        permissions=["cli"],
    )
    mock_registry.skills["future_tool"] = tool_incompatible
    step_incompatible = WorkflowStep(
        name="incompat_step",
        tool_name="future_tool",
    )
    plan_incompat = WorkflowPlan(
        name="incompatible_flow",
        workflow_id=uuid4(),
        steps=[step_incompatible],
    )
    with pytest.raises(JarvisSkillError, match="requires API version"):
        validator.validate(plan_incompat)

    # 8. Failure: invalid variable syntax reference check
    step_bad_syntax = WorkflowStep(
        name="bad_syntax",
        tool_name="cmd_exec",
        arguments={"arg": "{{steps.step_a.bad}}"},
    )
    plan_syntax = WorkflowPlan(
        name="bad_syntax_flow",
        workflow_id=uuid4(),
        steps=[step_bad_syntax],
    )
    with pytest.raises(ValueError, match="invalid variable reference"):
        validator.validate(plan_syntax)

    # 9. Failure: cycle detection (DAG validation)
    step_cycle1 = WorkflowStep(
        name="cycle_a",
        tool_name="cmd_exec",
        dependencies=["cycle_b"],
    )
    step_cycle2 = WorkflowStep(
        name="cycle_b",
        tool_name="cmd_exec",
        dependencies=["cycle_a"],
    )
    plan_cycle = WorkflowPlan(
        name="cyclic_dependencies",
        workflow_id=uuid4(),
        steps=[step_cycle1, step_cycle2],
    )
    with pytest.raises(ValueError, match="Circular dependency cycle detected"):
        validator.validate(plan_cycle)

    # 10. Failure: dependency on non-existent step
    step_missing_dep = WorkflowStep(
        name="orphan_step",
        tool_name="cmd_exec",
        dependencies=["missing_parent"],
    )
    plan_orphan = WorkflowPlan(
        name="orphan_flow",
        workflow_id=uuid4(),
        steps=[step_missing_dep],
    )
    with pytest.raises(ValueError, match="depends on non-existent step"):
        validator.validate(plan_orphan)

    # 11. Failure: empty step name
    step_empty_name = WorkflowStep(
        name="",
        tool_name="cmd_exec",
    )
    plan_empty_step_name = WorkflowPlan(
        name="empty_step_name",
        workflow_id=uuid4(),
        steps=[step_empty_name],
    )
    with pytest.raises(ValueError, match="Step name cannot be empty"):
        validator.validate(plan_empty_step_name)

    # 12. Success & Failure: template parameters inside list arguments
    step_list_ok = WorkflowStep(
        name="list_ok_step",
        tool_name="cmd_exec",
        arguments={"list_param": ["normal", "{{steps.step_a.output.var}}"]},
    )
    plan_list_ok = WorkflowPlan(
        name="list_ok",
        workflow_id=uuid4(),
        steps=[step1, step_list_ok],
    )
    validator.validate(plan_list_ok)

    step_list_bad = WorkflowStep(
        name="list_bad_step",
        tool_name="cmd_exec",
        arguments={"list_param": ["normal", "{{steps.step_a.bad}}"]},
    )
    plan_list_bad = WorkflowPlan(
        name="list_bad",
        workflow_id=uuid4(),
        steps=[step1, step_list_bad],
    )
    with pytest.raises(ValueError, match="invalid variable reference"):
        validator.validate(plan_list_bad)


def test_compiler_success_and_failures() -> None:
    """Verify that WorkflowCompiler handles topological sort, order validations, circular refs, and nesting depth."""
    compiler = WorkflowCompiler()

    # 1. Success compilation (resolving dependencies topologically)
    step_a = WorkflowStep(
        name="step_a",
        tool_name="cmd_exec",
        arguments={"cmd": "echo 1"},
    )
    step_b = WorkflowStep(
        name="step_b",
        tool_name="file_writer",
        arguments={"content": "{{steps.step_a.output.res}}"},
        dependencies=["step_a"],
    )
    step_c = WorkflowStep(
        name="step_c",
        tool_name="cmd_exec",
        arguments={"cmd_list": ["echo", "{{steps.step_a.output.res}}"]},
        dependencies=["step_a"],
    )
    plan = WorkflowPlan(
        name="compiler_ok",
        workflow_id=uuid4(),
        steps=[step_b, step_a, step_c],  # Unsorted order input
    )

    compiled = compiler.compile(plan)
    assert compiled.workflow_id == plan.workflow_id
    assert compiled.version == 1
    assert len(compiled.waves) == 2  # Wave 0: step_a, Wave 1: step_b, step_c
    assert compiled.waves[0] == [step_a]
    assert len(compiled.waves[1]) == 2
    assert step_b in compiled.waves[1]
    assert step_c in compiled.waves[1]

    # 2. Failure: Variable references non-existent step
    step_bad_ref = WorkflowStep(
        name="step_bad",
        tool_name="cmd_exec",
        arguments={"cmd": "{{steps.non_existent.output.res}}"},
    )
    plan_bad_ref = WorkflowPlan(
        name="bad_ref",
        workflow_id=uuid4(),
        steps=[step_bad_ref],
    )
    with pytest.raises(ValueError, match="references variable from non-existent step"):
        compiler.compile(plan_bad_ref)

    # 3. Failure: Variable references future step (execution order violation)
    step_future_ref_1 = WorkflowStep(
        name="first_step",
        tool_name="cmd_exec",
        arguments={"arg": "{{steps.second_step.output.val}}"},  # references future step
    )
    step_future_ref_2 = WorkflowStep(
        name="second_step",
        tool_name="cmd_exec",
        arguments={},
        dependencies=["first_step"],
    )
    plan_future = WorkflowPlan(
        name="future_ref",
        workflow_id=uuid4(),
        steps=[step_future_ref_1, step_future_ref_2],
    )
    with pytest.raises(ValueError, match="references future step"):
        compiler.compile(plan_future)

    # 4. Failure: Circular variable reference (Step A -> Step B -> Step A)
    step_circ_1 = WorkflowStep(
        name="circ_a",
        tool_name="cmd_exec",
        arguments={"arg": "{{steps.circ_b.output.val}}"},
        dependencies=["circ_b"],  # topological dependency allows circ_b first
    )
    step_circ_2 = WorkflowStep(
        name="circ_b",
        tool_name="cmd_exec",
        arguments={"arg": "{{steps.circ_a.output.val}}"},  # but references circ_a!
    )
    plan_circ = WorkflowPlan(
        name="circ_var",
        workflow_id=uuid4(),
        steps=[step_circ_1, step_circ_2],
    )
    with pytest.raises(ValueError, match="Circular variable reference chain detected"):
        compiler.compile(plan_circ)

    # 5. Failure: Variable nesting depth limit of 3 exceeded (A -> B -> C -> D)
    step_d = WorkflowStep(
        name="step_d",
        tool_name="cmd_exec",
        arguments={},
    )
    step_e = WorkflowStep(
        name="step_e",
        tool_name="cmd_exec",
        arguments={"arg": "{{steps.step_d.output.val}}"},
        dependencies=["step_d"],
    )
    step_f = WorkflowStep(
        name="step_f",
        tool_name="cmd_exec",
        arguments={"arg": "{{steps.step_e.output.val}}"},
        dependencies=["step_e"],
    )
    step_g = WorkflowStep(
        name="step_g",
        tool_name="cmd_exec",
        arguments={"arg": "{{steps.step_f.output.val}}"},  # Depth 4 lookup path!
        dependencies=["step_f"],
    )
    plan_depth = WorkflowPlan(
        name="depth_exceeded",
        workflow_id=uuid4(),
        steps=[step_d, step_e, step_f, step_g],
    )
    with pytest.raises(ValueError, match="depth limit of 3 exceeded"):
        compiler.compile(plan_depth)

    # 6. Failure: topological cycle detection (if double checked by compiler)
    step_cycle1 = WorkflowStep(
        name="cycle_a",
        tool_name="cmd_exec",
        dependencies=["cycle_b"],
    )
    step_cycle2 = WorkflowStep(
        name="cycle_b",
        tool_name="cmd_exec",
        dependencies=["cycle_a"],
    )
    plan_cycle = WorkflowPlan(
        name="cyclic_dependencies",
        workflow_id=uuid4(),
        steps=[step_cycle1, step_cycle2],
    )
    with pytest.raises(
        ValueError, match="Circular dependency detected during topological sorting"
    ):
        compiler.compile(plan_cycle)

    # 7. Failure: Compile plan with missing dependency (bypassing validator)
    step_orphan = WorkflowStep(
        name="orphan",
        tool_name="cmd_exec",
        dependencies=["non_existent"],
    )
    plan_orphan = WorkflowPlan(
        name="orphan_compile",
        workflow_id=uuid4(),
        steps=[step_orphan],
    )
    with pytest.raises(ValueError, match="depends on non-existent step"):
        compiler.compile(plan_orphan)


@pytest.fixture
async def db_session() -> Any:
    """Provides a transactional database session over an in-memory SQLite setup."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    # Create all tables (including workflows and workflow_versions tables)
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    async with db_manager.session() as session:
        yield session

    await db_manager.close()


@pytest.mark.asyncio
async def test_workflow_repository_operations(db_session: Any) -> None:
    """Verify CRUD, version history mapping, SHA-256 checks, and soft delete in WorkflowRepository."""
    repo = WorkflowRepository()
    workflow_id = uuid4()

    step_a = WorkflowStep(
        name="step_a",
        tool_name="cmd_exec",
        arguments={"cmd": "echo 1"},
    )
    plan = WorkflowPlan(
        name="Initial Workflow",
        workflow_id=workflow_id,
        steps=[step_a],
    )

    # 1. Create tables
    await repo.create_tables(db_session)

    # 2. Save Initial Workflow Plan (version 1)
    v1_dto = await repo.save(plan, db_session)
    assert v1_dto.version == 1
    assert v1_dto.workflow_id == workflow_id

    # 2. Get active workflow plan
    retrieved = await repo.get(workflow_id, db_session)
    assert retrieved is not None
    assert retrieved.name == "Initial Workflow"
    assert len(retrieved.steps) == 1

    # 3. Save identical plan (should return same version 1 and checksum)
    v1_dto_dup = await repo.save(plan, db_session)
    assert v1_dto_dup.version == 1
    assert v1_dto_dup.checksum == v1_dto.checksum

    # 4. Modify plan (different steps / arguments) and save -> version 2
    step_a_mod = WorkflowStep(
        name="step_a",
        tool_name="cmd_exec",
        arguments={"cmd": "echo updated"},
    )
    plan_mod = WorkflowPlan(
        name="Modified Workflow",
        workflow_id=workflow_id,
        steps=[step_a_mod],
    )
    v2_dto = await repo.save(plan_mod, db_session)
    assert v2_dto.version == 2
    assert v2_dto.checksum != v1_dto.checksum

    # 5. Get specifically version 1 and version 2
    plan_v1 = await repo.get_version(workflow_id, 1, db_session)
    assert plan_v1 is not None
    assert plan_v1.name == "Initial Workflow"

    plan_v2 = await repo.get_version(workflow_id, 2, db_session)
    assert plan_v2 is not None
    assert plan_v2.name == "Modified Workflow"

    # 6. List version logs
    versions_list = await repo.list_versions(workflow_id, db_session)
    assert len(versions_list) == 2
    assert versions_list[0].version == 1
    assert versions_list[1].version == 2

    # 7. List active workflows
    active_flows = await repo.list_active(db_session)
    assert len(active_flows) == 1
    assert active_flows[0].name == "Modified Workflow"

    # 8. Soft Delete active workflow
    deleted_ok = await repo.delete(workflow_id, db_session)
    assert deleted_ok is True

    # 9. Query soft-deleted active -> should return None
    assert await repo.get(workflow_id, db_session) is None

    # Retrieve soft-deleted again -> returns False
    deleted_fail = await repo.delete(workflow_id, db_session)
    assert deleted_fail is False

    # 10. List active workflows -> should be empty
    active_flows_post = await repo.list_active(db_session)
    assert len(active_flows_post) == 0

    # 11. Retrieve historical versions -> should still be accessible
    versions_post = await repo.list_versions(workflow_id, db_session)
    assert len(versions_post) == 2

    plan_v1_post = await repo.get_version(workflow_id, 1, db_session)
    assert plan_v1_post is not None
    assert plan_v1_post.name == "Initial Workflow"

    # 12. Non-existent workflow lookups -> return None
    fake_id = uuid4()
    assert await repo.get(fake_id, db_session) is None
    assert await repo.get_version(fake_id, 1, db_session) is None


@pytest.mark.asyncio
async def test_workflow_orchestrator_scenarios() -> None:
    """Verify that WorkflowOrchestrator manages execution waves, recovery policies, and bindings resolution."""
    from unittest.mock import AsyncMock, MagicMock

    mock_exec_orchestrator = MagicMock(spec=ExecutionOrchestrator)
    mock_event_bus = AsyncMock(spec=EventBusInterface)

    orchestrator = WorkflowOrchestrator(
        orchestrator=mock_exec_orchestrator,
        event_bus=mock_event_bus,
    )

    session = ReasoningSession(uuid4(), uuid4())
    workflow_id = uuid4()

    # 1. Success execution with variable binding
    step_a = WorkflowStep(
        name="step_a",
        tool_name="cmd_exec",
        arguments={"cmd": "echo hello"},
    )
    step_b = WorkflowStep(
        name="step_b",
        tool_name="file_writer",
        arguments={"content": "{{steps.step_a.output.result}}"},
    )
    # CompiledWorkflow wave ordering
    compiled = CompiledWorkflow(
        workflow_id=workflow_id,
        version=1,
        waves=[[step_a], [step_b]],
    )

    # Mock execute_task_step outcomes
    mock_exec_orchestrator.execute_task_step = AsyncMock(
        side_effect=[
            {"result": "hello_stdout"},  # step_a output
            {"success": True},  # step_b output
        ]
    )

    res = await orchestrator.execute_workflow(compiled, session)
    assert res["status"] == "SUCCESS"
    assert res["state"] == WorkflowState.COMPLETED
    assert res["step_outputs"]["step_a"] == {"result": "hello_stdout"}
    assert res["step_outputs"]["step_b"] == {"success": True}

    # Verify mock_exec_orchestrator calls (variable resolved correctly!)
    assert mock_exec_orchestrator.execute_task_step.call_count == 2
    mock_exec_orchestrator.execute_task_step.assert_any_call(
        tool_name="cmd_exec",
        arguments={"cmd": "echo hello"},
        session=session,
        caller_id="workflow_orchestrator",
    )
    mock_exec_orchestrator.execute_task_step.assert_any_call(
        tool_name="file_writer",
        arguments={"content": "hello_stdout"},  # resolved from step_a output!
        session=session,
        caller_id="workflow_orchestrator",
    )

    # Verify event bus transition messages
    assert (
        mock_event_bus.publish.call_count >= 6
    )  # started, step_started, step_completed, step_started, step_completed, completed

    # 2. Failure execution: step failure with RecoveryPolicy.STOP
    step_fail = WorkflowStep(
        name="step_fail",
        tool_name="cmd_exec",
        recovery_policy=RecoveryPolicy.STOP,
    )
    compiled_fail = CompiledWorkflow(
        workflow_id=uuid4(),
        version=1,
        waves=[[step_fail]],
    )
    mock_exec_orchestrator.execute_task_step = AsyncMock(
        side_effect=ValueError("crashed")
    )
    res_fail = await orchestrator.execute_workflow(compiled_fail, session)
    assert res_fail["status"] == "FAILURE"
    assert res_fail["state"] == WorkflowState.FAILED
    assert "crashed" in res_fail["error"]

    # 3. Success execution with RecoveryPolicy.CONTINUE
    step_fail_continue = WorkflowStep(
        name="step_fail_continue",
        tool_name="cmd_exec",
        recovery_policy=RecoveryPolicy.CONTINUE,
    )
    step_next = WorkflowStep(
        name="step_next",
        tool_name="file_writer",
    )
    compiled_continue = CompiledWorkflow(
        workflow_id=uuid4(),
        version=1,
        waves=[[step_fail_continue], [step_next]],
    )
    mock_exec_orchestrator.execute_task_step = AsyncMock(
        side_effect=[ValueError("crashed but continue"), {"done": True}]
    )
    res_continue = await orchestrator.execute_workflow(compiled_continue, session)
    assert res_continue["status"] == "SUCCESS"
    assert res_continue["state"] == WorkflowState.COMPLETED
    assert "error" in res_continue["step_outputs"]["step_fail_continue"]
    assert res_continue["step_outputs"]["step_next"] == {"done": True}

    # 4. Success execution with RecoveryPolicy.RETRY_STEP
    step_retry = WorkflowStep(
        name="step_retry",
        tool_name="cmd_exec",
        recovery_policy=RecoveryPolicy.RETRY_STEP,
    )
    compiled_retry = CompiledWorkflow(
        workflow_id=uuid4(),
        version=1,
        waves=[[step_retry]],
    )
    mock_exec_orchestrator.execute_task_step = AsyncMock(
        side_effect=[
            ValueError("first try failed"),
            ValueError("second try failed"),
            {"success": "retry works"},
        ]
    )
    res_retry = await orchestrator.execute_workflow(compiled_retry, session)
    assert res_retry["status"] == "SUCCESS"
    assert res_retry["state"] == WorkflowState.COMPLETED
    assert res_retry["step_outputs"]["step_retry"] == {"success": "retry works"}
    assert res_retry["metrics"].retry_count == 2

    # 5. Success execution with complex template types (nested list, dict, and string substitution)
    step_complex_a = WorkflowStep(
        name="step_a",
        tool_name="cmd_exec",
        arguments={},
    )
    step_complex_b = WorkflowStep(
        name="step_b",
        tool_name="file_writer",
        arguments={
            "string_sub": "value: {{steps.step_a.output.res1}} and {{steps.step_a.output.res2}}",
            "list_sub": ["{{steps.step_a.output.res1}}", "static"],
            "dict_sub": {"nested_key": "{{steps.step_a.output.res2}}"},
            "int_val": 42,
        },
        dependencies=["step_a"],
    )
    compiled_complex = CompiledWorkflow(
        workflow_id=uuid4(),
        version=1,
        waves=[[step_complex_a], [step_complex_b]],
    )

    mock_exec_orchestrator.execute_task_step = AsyncMock(
        side_effect=[{"res1": "apple", "res2": "orange"}, {"done": True}]
    )

    res_complex = await orchestrator.execute_workflow(compiled_complex, session)
    assert res_complex["status"] == "SUCCESS"
    mock_exec_orchestrator.execute_task_step.assert_any_call(
        tool_name="file_writer",
        arguments={
            "string_sub": "value: apple and orange",
            "list_sub": ["apple", "static"],
            "dict_sub": {"nested_key": "orange"},
            "int_val": 42,
        },
        session=session,
        caller_id="workflow_orchestrator",
    )

    # 6. Variable resolution failure (missing variable name in outputs)
    step_bad_eval_a = WorkflowStep(
        name="step_a",
        tool_name="cmd_exec",
        arguments={},
    )
    step_bad_eval_b = WorkflowStep(
        name="step_b",
        tool_name="cmd_exec",
        arguments={"arg": "{{steps.step_a.output.missing_var}}"},
        dependencies=["step_a"],
    )
    compiled_bad_eval = CompiledWorkflow(
        workflow_id=uuid4(),
        version=1,
        waves=[[step_bad_eval_a], [step_bad_eval_b]],
    )
    mock_exec_orchestrator.execute_task_step = AsyncMock(
        side_effect=[{"res": "value"}, {"done": True}]
    )
    res_bad = await orchestrator.execute_workflow(compiled_bad_eval, session)
    assert res_bad["status"] == "FAILURE"
    assert "missing_var" in res_bad["error"]

    # 7. Variable resolution failure (invalid template format string substitution)
    step_bad_format = WorkflowStep(
        name="step_b",
        tool_name="cmd_exec",
        arguments={"arg": "path: {{steps.step_a.bad}}"},
        dependencies=["step_a"],
    )
    compiled_bad_format = CompiledWorkflow(
        workflow_id=uuid4(),
        version=1,
        waves=[[step_bad_eval_a], [step_bad_format]],
    )
    mock_exec_orchestrator.execute_task_step = AsyncMock(return_value={"res": "value"})
    res_bad_format = await orchestrator.execute_workflow(compiled_bad_format, session)
    assert res_bad_format["status"] == "FAILURE"
    assert "Invalid template format" in res_bad_format["error"]

    # 8. Single-template invalid format (covers line 247: VAR_PATTERN no match in exact-template branch)
    step_single_bad_fmt = WorkflowStep(
        name="step_b",
        tool_name="cmd_exec",
        # A template that matches ANY_TEMPLATE_PATTERN but not VAR_PATTERN (missing ref_var dot)
        arguments={"arg": "{{steps.step_a.bad}}"},
        dependencies=["step_a"],
    )
    compiled_single_bad_fmt = CompiledWorkflow(
        workflow_id=uuid4(),
        version=1,
        waves=[[step_bad_eval_a], [step_single_bad_fmt]],
    )
    mock_exec_orchestrator.execute_task_step = AsyncMock(return_value={"res": "ok"})
    res_single_bad_fmt = await orchestrator.execute_workflow(
        compiled_single_bad_fmt, session
    )
    assert res_single_bad_fmt["status"] == "FAILURE"
    assert "Invalid template format" in res_single_bad_fmt["error"]

    # 9. Single-template step reference not yet executed (covers line 252)
    step_missing_ref = WorkflowStep(
        name="step_b",
        tool_name="cmd_exec",
        # References a step that doesn't exist in step_outputs
        arguments={"arg": "{{steps.nonexistent.output.val}}"},
    )
    compiled_missing_ref = CompiledWorkflow(
        workflow_id=uuid4(),
        version=1,
        # Single wave so step_b has no prior step_a to execute first
        waves=[[step_missing_ref]],
    )
    mock_exec_orchestrator.execute_task_step = AsyncMock(return_value={"res": "ok"})
    res_missing_ref = await orchestrator.execute_workflow(compiled_missing_ref, session)
    assert res_missing_ref["status"] == "FAILURE"
    assert "has not executed yet" in res_missing_ref["error"]

    # 10. Multi-template: first template resolves but second references step not executed (line 268)
    step_multi_missing_step = WorkflowStep(
        name="step_b",
        tool_name="cmd_exec",
        # Two templates — second references a step that hasn't run
        arguments={"arg": "{{steps.step_a.output.res}} and {{steps.ghost.output.res}}"},
        dependencies=["step_a"],
    )
    compiled_multi_missing_step = CompiledWorkflow(
        workflow_id=uuid4(),
        version=1,
        waves=[[step_bad_eval_a], [step_multi_missing_step]],
    )
    mock_exec_orchestrator.execute_task_step = AsyncMock(return_value={"res": "value"})
    res_multi_missing_step = await orchestrator.execute_workflow(
        compiled_multi_missing_step, session
    )
    assert res_multi_missing_step["status"] == "FAILURE"
    assert "has not executed yet" in res_multi_missing_step["error"]

    # 11. Multi-template: step is in outputs but referenced variable is missing (line 271)
    step_multi_missing_var = WorkflowStep(
        name="step_b",
        tool_name="cmd_exec",
        # Two templates — step_a ran but doesn't have "missing_key"
        arguments={
            "arg": "{{steps.step_a.output.res}} {{steps.step_a.output.missing_key}}"
        },
        dependencies=["step_a"],
    )
    compiled_multi_missing_var = CompiledWorkflow(
        workflow_id=uuid4(),
        version=1,
        waves=[[step_bad_eval_a], [step_multi_missing_var]],
    )
    mock_exec_orchestrator.execute_task_step = AsyncMock(return_value={"res": "value"})
    res_multi_missing_var = await orchestrator.execute_workflow(
        compiled_multi_missing_var, session
    )
    assert res_multi_missing_var["status"] == "FAILURE"
    assert "missing_key" in res_multi_missing_var["error"]

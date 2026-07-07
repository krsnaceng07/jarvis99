"""JARVIS OS - Reasoning Execution Engine Integration & Unit Tests.

Validates the goal execution loop, state machine transitions, budget checkpoints, reflection decision paths, and plan history version tracking.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.config import Settings
from core.exceptions import BudgetExceededError
from core.interfaces import EventBusInterface
from core.reasoning.cost import CostGovernor
from core.reasoning.engine import ReasoningExecutionEngine
from core.reasoning.engine_dto import (
    ExecutionPlan,
    FailureType,
    RiskLevel,
    SessionState,
)
from core.reasoning.orchestrator import ExecutionOrchestrator
from core.reasoning.plan_version_manager import PlanVersionManager
from core.reasoning.planner import ReasoningSession
from core.reasoning.planning_service import PlanningService
from core.reasoning.prompt import PromptBuilder
from core.reasoning.reflection import ReflectionEngine
from core.reasoning.router import ModelRouter
from core.tools.dto import AggregatedWaveResult, ExecutionWave, WaveTask


@pytest.mark.asyncio
async def test_engine_successful_execution_path() -> None:
    """Verify execution engine runs goal decomposition, runs waves, and completes successfully."""
    settings = Settings.load_settings()

    # Mocks
    mock_orchestrator = MagicMock(spec=ExecutionOrchestrator)
    mock_reflection = MagicMock(spec=ReflectionEngine)
    mock_router = MagicMock(spec=ModelRouter)
    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_cost_gov = MagicMock(spec=CostGovernor)
    mock_event_bus = AsyncMock(spec=EventBusInterface)

    # Setup dummy planner output
    task1 = WaveTask(
        task_id=uuid4(),
        idempotency_key=uuid4(),
        tool_name="cmd_executor",
        arguments={},
        priority=1,
    )
    task2 = WaveTask(
        task_id=uuid4(),
        idempotency_key=uuid4(),
        tool_name="file_writer",
        arguments={},
        priority=1,
    )
    wave1 = ExecutionWave(wave_id=uuid4(), tasks=[task1], status="PENDING")
    wave2 = ExecutionWave(wave_id=uuid4(), tasks=[task2], status="PENDING")
    initial_plan = ExecutionPlan(
        goal="Run command, write file",
        trace_id=uuid4(),
        waves=[wave1, wave2],
        estimated_cost=Decimal("0.10"),
    )

    mock_planning_service = MagicMock(spec=PlanningService)
    mock_planning_service.generate_initial_plan = AsyncMock(return_value=initial_plan)

    # Setup successful wave execution result
    mock_wave_res = AggregatedWaveResult(
        wave_id=wave1.wave_id,
        status="SUCCESS",
        combined_stdout="done",
        combined_stderr="",
        total_duration=1.0,
        artifacts={},
    )
    mock_orchestrator.execute_wave = AsyncMock(return_value=mock_wave_res)

    version_manager = PlanVersionManager()

    engine = ReasoningExecutionEngine(
        orchestrator=mock_orchestrator,
        reflection_engine=mock_reflection,
        router=mock_router,
        prompt_builder=mock_prompt_builder,
        cost_governor=mock_cost_gov,
        settings=settings,
        planning_service=mock_planning_service,
        version_manager=version_manager,
        event_bus=mock_event_bus,
    )

    res = await engine.execute_goal("Run command, write file")

    assert res["status"] == "SUCCESS"
    assert res["state"] == SessionState.COMPLETED
    assert res["waves_executed"] == 2
    assert res["plan_version"] == 1

    # Verify event transitions published
    assert mock_event_bus.publish.call_count >= 3
    # Check that transition to COMPLETED event was broadcast
    last_call = mock_event_bus.publish.call_args_list[-1]
    assert last_call[0][0] == "engine.state.transition"
    assert last_call[0][1].body["state"] == SessionState.COMPLETED.value


@pytest.mark.asyncio
async def test_engine_budget_checkpoint_exhausted() -> None:
    """Verify execution engine aborts when budget checkpoint limits are exceeded."""
    settings = Settings.load_settings()

    mock_orchestrator = MagicMock(spec=ExecutionOrchestrator)
    mock_reflection = MagicMock(spec=ReflectionEngine)
    mock_router = MagicMock(spec=ModelRouter)
    mock_prompt_builder = MagicMock(spec=PromptBuilder)

    # Force BudgetExceededError in CostGovernor
    mock_cost_gov = MagicMock(spec=CostGovernor)
    mock_cost_gov.check_budget_limits = AsyncMock(
        side_effect=BudgetExceededError(code="BUDGET_001", message="Exceeded")
    )

    mock_planning_service = MagicMock(spec=PlanningService)
    version_manager = PlanVersionManager()

    engine = ReasoningExecutionEngine(
        orchestrator=mock_orchestrator,
        reflection_engine=mock_reflection,
        router=mock_router,
        prompt_builder=mock_prompt_builder,
        cost_governor=mock_cost_gov,
        settings=settings,
        planning_service=mock_planning_service,
        version_manager=version_manager,
    )

    res = await engine.execute_goal("Run goal")

    assert res["status"] == "FAILURE"
    assert res["state"] == SessionState.FAILED
    assert res["failure_type"] == FailureType.BudgetFailure
    assert "Exceeded" in res["error"]


@pytest.mark.asyncio
async def test_plan_version_manager_diff() -> None:
    """Verify PlanVersionManager computes structured added, removed, and modified tasks diffs."""
    task1 = WaveTask(
        task_id=uuid4(),
        idempotency_key=uuid4(),
        tool_name="cmd_executor",
        arguments={"cmd": "run"},
        priority=1,
    )
    task2 = WaveTask(
        task_id=uuid4(),
        idempotency_key=uuid4(),
        tool_name="file_writer",
        arguments={"path": "a.txt"},
        priority=1,
    )

    wave1 = ExecutionWave(wave_id=uuid4(), tasks=[task1], status="COMPLETED")
    wave2 = ExecutionWave(wave_id=uuid4(), tasks=[task2], status="PENDING")

    plan1 = ExecutionPlan(
        goal="Do something",
        trace_id=uuid4(),
        waves=[wave1, wave2],
        plan_version=1,
    )

    # Replaced task2 with a modified task, and added task3
    task2_modified = WaveTask(
        task_id=task2.task_id,
        idempotency_key=uuid4(),
        tool_name="file_writer",
        arguments={"path": "b.txt"},  # Changed argument
        priority=1,
    )
    task3 = WaveTask(
        task_id=uuid4(),
        idempotency_key=uuid4(),
        tool_name="telemetry",
        arguments={},
        priority=1,
    )

    wave2_new = ExecutionWave(
        wave_id=wave2.wave_id, tasks=[task2_modified], status="PENDING"
    )
    wave3 = ExecutionWave(wave_id=uuid4(), tasks=[task3], status="PENDING")

    plan2 = ExecutionPlan(
        goal="Do something",
        trace_id=plan1.trace_id,
        waves=[wave1, wave2_new, wave3],
        plan_version=2,
    )

    manager = PlanVersionManager()
    manager.create_version(plan1)
    manager.create_version(plan2)

    diff_dict = manager.diff(plan1, plan2)

    assert diff_dict["old_version"] == 1
    assert diff_dict["new_version"] == 2
    assert len(diff_dict["added_tasks"]) == 1
    assert diff_dict["added_tasks"][0]["tool_name"] == "telemetry"
    assert len(diff_dict["modified_tasks"]) == 1
    assert diff_dict["modified_tasks"][0]["changes"]["new_args"] == {"path": "b.txt"}


@pytest.mark.asyncio
async def test_engine_reflection_repair_loop() -> None:
    """Verify failed tasks trigger reflection, and RETRY decisions invoke planning service repairs."""
    settings = Settings.load_settings()

    mock_orchestrator = MagicMock(spec=ExecutionOrchestrator)
    mock_router = MagicMock(spec=ModelRouter)
    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_cost_gov = MagicMock(spec=CostGovernor)

    # Setup reflection engine mocks: first returns RETRY, second returns SUCCESS
    mock_reflection = MagicMock(spec=ReflectionEngine)
    mock_reflection.reflect_and_correct = AsyncMock(
        side_effect=[
            {"status": "RETRY", "reflection_count": 1},
            {"status": "SUCCESS", "reflection_count": 2},
        ]
    )

    task1 = WaveTask(
        task_id=uuid4(),
        idempotency_key=uuid4(),
        tool_name="cmd_executor",
        arguments={},
        priority=1,
    )
    wave1 = ExecutionWave(wave_id=uuid4(), tasks=[task1], status="PENDING")

    plan1 = ExecutionPlan(
        goal="Repair test",
        trace_id=uuid4(),
        waves=[wave1],
        plan_version=1,
    )

    mock_planning_service = MagicMock(spec=PlanningService)
    mock_planning_service.generate_initial_plan = AsyncMock(return_value=plan1)

    # Repair plan version 2
    plan2 = ExecutionPlan(
        goal="Repair test",
        trace_id=plan1.trace_id,
        waves=[wave1],
        plan_version=2,
    )
    mock_planning_service.repair_plan = AsyncMock(return_value=plan2)

    # Orchestrator first fails, then succeeds
    res_fail = AggregatedWaveResult(
        wave_id=wave1.wave_id,
        status="FAILURE",
        combined_stdout="",
        combined_stderr="error log",
        total_duration=0.5,
        artifacts={},
    )
    res_success = AggregatedWaveResult(
        wave_id=wave1.wave_id,
        status="SUCCESS",
        combined_stdout="healed",
        combined_stderr="",
        total_duration=0.5,
        artifacts={},
    )
    mock_orchestrator.execute_wave = AsyncMock(side_effect=[res_fail, res_success])

    version_manager = PlanVersionManager()

    engine = ReasoningExecutionEngine(
        orchestrator=mock_orchestrator,
        reflection_engine=mock_reflection,
        router=mock_router,
        prompt_builder=mock_prompt_builder,
        cost_governor=mock_cost_gov,
        settings=settings,
        planning_service=mock_planning_service,
        version_manager=version_manager,
    )

    res = await engine.execute_goal("Repair test")

    assert res["status"] == "SUCCESS"
    assert res["plan_version"] == 2
    assert mock_orchestrator.execute_wave.call_count == 2
    assert mock_reflection.reflect_and_correct.call_count == 1


@pytest.mark.asyncio
async def test_planning_service_methods() -> None:
    """Verify PlanningService generate_initial_plan and repair_plan execute actual business logic."""
    mock_router = MagicMock(spec=ModelRouter)
    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_cost_gov = MagicMock(spec=CostGovernor)

    mock_provider = MagicMock()
    mock_provider.name = "TestLlama"
    mock_provider.model_name = "llama-3"
    mock_provider.generate = AsyncMock(return_value="Task A, Task B")
    mock_provider.count_tokens = MagicMock(return_value=100)

    mock_router.get_provider_for_task = AsyncMock(return_value=mock_provider)
    mock_prompt_builder.build_prompt = MagicMock(
        return_value="compiled user goal prompt"
    )
    mock_cost_gov.estimate_cost = MagicMock(return_value=Decimal("0.05"))
    mock_cost_gov.check_budget_limits = AsyncMock()
    mock_cost_gov.log_usage = AsyncMock(return_value=Decimal("0.04"))

    planning_service = PlanningService(
        router=mock_router,
        prompt_builder=mock_prompt_builder,
        cost_governor=mock_cost_gov,
    )

    session = ReasoningSession(uuid4(), uuid4())
    trace_id = uuid4()

    # Test initial plan generation
    plan = await planning_service.generate_initial_plan(
        goal="run a test, write report",
        session=session,
        trace_id=trace_id,
        memories_list=["memory context"],
    )

    assert plan.goal == "run a test, write report"
    assert plan.plan_version == 1
    assert len(plan.waves) == 1
    assert len(plan.waves[0].tasks) == 2
    assert plan.estimated_cost == Decimal("0.05")

    # Test plan repair
    failed_task = WaveTask(
        task_id=uuid4(),
        idempotency_key=uuid4(),
        tool_name="cmd_executor",
        arguments={},
        priority=1,
    )
    repaired_plan = await planning_service.repair_plan(
        current_plan=plan,
        failed_tasks=[failed_task],
        session=session,
    )

    assert repaired_plan.plan_version == 2
    assert len(repaired_plan.waves) == 1
    assert repaired_plan.risk_level == RiskLevel.HIGH


@pytest.mark.asyncio
async def test_plan_version_manager_rollback_exception() -> None:
    """Verify PlanVersionManager throws KeyError on missing rollback versions."""
    manager = PlanVersionManager()
    assert manager.current_version() == 0

    with pytest.raises(KeyError, match="Plan version 99 not found"):
        manager.rollback(99)


@pytest.mark.asyncio
async def test_engine_aborted_paths() -> None:
    """Verify execution engine abort paths for planning failures and reflection abort decisions."""
    settings = Settings.load_settings()

    mock_orchestrator = MagicMock(spec=ExecutionOrchestrator)
    mock_router = MagicMock(spec=ModelRouter)
    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_cost_gov = MagicMock(spec=CostGovernor)
    mock_cost_gov.check_budget_limits = AsyncMock()

    # Setup reflection engine to return ABORT
    mock_reflection = MagicMock(spec=ReflectionEngine)
    mock_reflection.reflect_and_correct = AsyncMock(return_value={"status": "ABORT"})

    task1 = WaveTask(
        task_id=uuid4(),
        idempotency_key=uuid4(),
        tool_name="cmd_executor",
        arguments={},
        priority=1,
    )
    wave1 = ExecutionWave(wave_id=uuid4(), tasks=[task1], status="PENDING")

    plan1 = ExecutionPlan(
        goal="Abort test",
        trace_id=uuid4(),
        waves=[wave1],
        plan_version=1,
    )

    # 1. Test planning failure abort
    mock_planning_service_fail = MagicMock(spec=PlanningService)
    mock_planning_service_fail.generate_initial_plan = AsyncMock(
        side_effect=ValueError("Planning error")
    )

    version_manager = PlanVersionManager()
    engine_fail = ReasoningExecutionEngine(
        orchestrator=mock_orchestrator,
        reflection_engine=mock_reflection,
        router=mock_router,
        prompt_builder=mock_prompt_builder,
        cost_governor=mock_cost_gov,
        settings=settings,
        planning_service=mock_planning_service_fail,
        version_manager=version_manager,
    )

    res_fail = await engine_fail.execute_goal("Abort test")
    assert res_fail["status"] == "FAILURE"
    assert (
        res_fail["failure_type"] == FailureType.ModelFailure
        or res_fail["failure_type"] == FailureType.PlannerFailure
    )

    # 2. Test reflection abort decision path
    mock_planning_service_ok = MagicMock(spec=PlanningService)
    mock_planning_service_ok.generate_initial_plan = AsyncMock(return_value=plan1)

    mock_wave_fail = AggregatedWaveResult(
        wave_id=wave1.wave_id,
        status="FAILURE",
        combined_stdout="",
        combined_stderr="error log",
        total_duration=0.5,
        artifacts={},
    )
    mock_orchestrator.execute_wave = AsyncMock(return_value=mock_wave_fail)

    engine_abort = ReasoningExecutionEngine(
        orchestrator=mock_orchestrator,
        reflection_engine=mock_reflection,
        router=mock_router,
        prompt_builder=mock_prompt_builder,
        cost_governor=mock_cost_gov,
        settings=settings,
        planning_service=mock_planning_service_ok,
        version_manager=version_manager,
    )

    res_abort = await engine_abort.execute_goal("Abort test")
    assert res_abort["status"] == "FAILURE"
    assert res_abort["failure_type"] == FailureType.ReflectionFailure


@pytest.mark.asyncio
async def test_engine_db_and_failures() -> None:
    """Verify db logging calls and orchestrator/repair exception handling in execution engine."""
    settings = Settings.load_settings()

    mock_orchestrator = MagicMock(spec=ExecutionOrchestrator)
    mock_router = MagicMock(spec=ModelRouter)
    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_cost_gov = MagicMock(spec=CostGovernor)

    # Mock DB session
    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    mock_reflection = MagicMock(spec=ReflectionEngine)
    mock_reflection.reflect_and_correct = AsyncMock(return_value={"status": "RETRY"})

    task1 = WaveTask(
        task_id=uuid4(),
        idempotency_key=uuid4(),
        tool_name="cmd_executor",
        arguments={},
        priority=1,
    )
    wave1 = ExecutionWave(wave_id=uuid4(), tasks=[task1], status="PENDING")
    plan1 = ExecutionPlan(
        goal="DB test",
        trace_id=uuid4(),
        waves=[wave1],
        plan_version=1,
    )

    mock_planning_service = MagicMock(spec=PlanningService)
    mock_planning_service.generate_initial_plan = AsyncMock(return_value=plan1)

    # 1. Database session success execution path (covers DB writes)
    mock_wave_ok = AggregatedWaveResult(
        wave_id=wave1.wave_id,
        status="SUCCESS",
        combined_stdout="done",
        combined_stderr="",
        total_duration=0.5,
        artifacts={},
    )
    mock_orchestrator.execute_wave = AsyncMock(return_value=mock_wave_ok)

    version_manager = PlanVersionManager()
    engine = ReasoningExecutionEngine(
        orchestrator=mock_orchestrator,
        reflection_engine=mock_reflection,
        router=mock_router,
        prompt_builder=mock_prompt_builder,
        cost_governor=mock_cost_gov,
        settings=settings,
        planning_service=mock_planning_service,
        version_manager=version_manager,
    )

    res = await engine.execute_goal("DB test", db_session=mock_db)
    assert res["status"] == "SUCCESS"
    assert mock_db.flush.call_count > 0

    # 2. Test Checkpoint 2/3/4 Budget check failures
    mock_cost_gov.check_budget_limits = AsyncMock(
        side_effect=[
            None,
            BudgetExceededError(code="BUDGET_001", message="Checkpoint budget failed"),
        ]
    )
    res_budget = await engine.execute_goal("DB test")
    assert res_budget["status"] == "FAILURE"
    assert res_budget["failure_type"] == FailureType.BudgetFailure

    # 3. Test Orchestrator exception path
    mock_cost_gov.check_budget_limits = AsyncMock(return_value=None)
    mock_orchestrator.execute_wave = AsyncMock(
        side_effect=RuntimeError("Runtime execution crashed")
    )
    res_crash = await engine.execute_goal("DB test")
    assert res_crash["status"] == "FAILURE"
    assert res_crash["failure_type"] == FailureType.ToolFailure

    # 4. Test Planning repair exception path
    mock_wave_fail = AggregatedWaveResult(
        wave_id=wave1.wave_id,
        status="FAILURE",
        combined_stdout="",
        combined_stderr="fail",
        total_duration=0.5,
        artifacts={},
    )
    mock_orchestrator.execute_wave = AsyncMock(return_value=mock_wave_fail)
    mock_planning_service.repair_plan = AsyncMock(
        side_effect=ValueError("Repair logic failed")
    )
    res_repair_fail = await engine.execute_goal("DB test")
    assert res_repair_fail["status"] == "FAILURE"
    assert res_repair_fail["failure_type"] == FailureType.PlannerFailure

"""
PHASE: 22
STATUS: TEST
SPECIFICATION:
    docs/82_PHASE_22_ORCHESTRATOR_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 22 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.config import Settings
from core.interfaces import EventBusInterface
from core.reasoning.cost import CostGovernor
from core.reasoning.dispatcher import ToolDispatcher
from core.reasoning.engine import ReasoningExecutionEngine
from core.reasoning.engine_dto import FailureType
from core.reasoning.orchestrator import ExecutionOrchestrator
from core.reasoning.plan_version_manager import PlanVersionManager
from core.reasoning.planner import ReasoningSession
from core.reasoning.planning_service import PlanningService
from core.reasoning.prompt import PromptBuilder
from core.reasoning.reflection import ReflectionEngine
from core.reasoning.router import ModelRouter
from core.reasoning.task import ExecutorType, Task, TaskStatus, TaskType
from core.tools.dto import ToolExecutionResult


@pytest.mark.asyncio
async def test_orchestrator_task_retry_success() -> None:
    """Verify dispatcher retry: fails twice then succeeds on third attempt."""
    mock_event_bus = AsyncMock(spec=EventBusInterface)
    orchestrator = ExecutionOrchestrator(
        tool_runtime=MagicMock(),
        settings=Settings.load_settings(),
        event_bus=mock_event_bus,
    )

    mock_dispatcher = MagicMock(spec=ToolDispatcher)
    fail_res = ToolExecutionResult(task_id=uuid4(), status="FAILURE", exit_code=1)
    success_res = ToolExecutionResult(task_id=uuid4(), status="SUCCESS", exit_code=0)
    mock_dispatcher.dispatch = AsyncMock(side_effect=[fail_res, fail_res, success_res])

    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        task_type=TaskType.CODE,
        executor=ExecutorType.PYTHON,
        payload={"code": "flaky_run"},
        status=TaskStatus.PENDING,
    )
    session = ReasoningSession(uuid4(), uuid4())

    res = await orchestrator.execute_task_step_new(
        task=task,
        session=session,
        dispatcher=mock_dispatcher,
        context={},
    )

    assert res.status == "SUCCESS"
    assert task.status == TaskStatus.SUCCESS
    assert mock_dispatcher.dispatch.call_count == 3


@pytest.mark.asyncio
async def test_orchestrator_task_retry_exhausted() -> None:
    """Verify dispatcher exhausts 3 retries and returns FAILURE."""
    mock_event_bus = AsyncMock(spec=EventBusInterface)
    orchestrator = ExecutionOrchestrator(
        tool_runtime=MagicMock(),
        settings=Settings.load_settings(),
        event_bus=mock_event_bus,
    )

    mock_dispatcher = MagicMock(spec=ToolDispatcher)
    fail_res = ToolExecutionResult(task_id=uuid4(), status="FAILURE", exit_code=1)
    mock_dispatcher.dispatch = AsyncMock(return_value=fail_res)

    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        task_type=TaskType.CODE,
        executor=ExecutorType.PYTHON,
        payload={"code": "always_fails"},
        status=TaskStatus.PENDING,
    )
    session = ReasoningSession(uuid4(), uuid4())

    res = await orchestrator.execute_task_step_new(
        task=task,
        session=session,
        dispatcher=mock_dispatcher,
        context={},
    )

    assert res.status == "FAILURE"
    assert task.status == TaskStatus.FAILED
    assert mock_dispatcher.dispatch.call_count == 3


@pytest.mark.asyncio
async def test_engine_execute_goal_new_wave_failure() -> None:
    """Verify execute_goal_new aborts on wave FAILURE."""
    settings = Settings.load_settings()

    mock_orchestrator = MagicMock(spec=ExecutionOrchestrator)
    mock_reflection = MagicMock(spec=ReflectionEngine)
    mock_router = MagicMock(spec=ModelRouter)
    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_cost_gov = MagicMock(spec=CostGovernor)
    mock_event_bus = AsyncMock(spec=EventBusInterface)

    mock_cost_gov.check_budget_limits = AsyncMock()

    from core.tools.dto import AggregatedWaveResult

    mock_wave_fail = AggregatedWaveResult(
        wave_id=uuid4(),
        status="FAILURE",
        tasks_completed=[],
        tasks_failed=[uuid4()],
        combined_stdout="",
        combined_stderr="something went wrong",
        total_duration=0.5,
        artifacts={},
    )
    mock_orchestrator.execute_wave_new = AsyncMock(return_value=mock_wave_fail)
    mock_orchestrator.event_bus = mock_event_bus

    version_manager = PlanVersionManager()
    mock_planning_service = MagicMock(spec=PlanningService)

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

    res = await engine.execute_goal_new(
        goal="Run command",
        budget=5.0,
    )

    assert res["status"] == "FAILURE"
    assert res["failure_type"] == FailureType.ToolFailure
    assert "failed" in res["error"]

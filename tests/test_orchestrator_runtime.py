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
from core.reasoning.engine import ReasoningExecutionEngine
from core.reasoning.engine_dto import SessionState
from core.reasoning.orchestrator import ExecutionOrchestrator
from core.reasoning.plan_version_manager import PlanVersionManager
from core.reasoning.planning_service import PlanningService
from core.reasoning.prompt import PromptBuilder
from core.reasoning.reflection import ReflectionEngine
from core.reasoning.router import ModelRouter


@pytest.mark.asyncio
async def test_engine_execute_goal_new_success() -> None:
    """Verify the full E2E new execution path: memory → planner → orchestrator → success."""
    settings = Settings.load_settings()

    # Create Mocks
    mock_orchestrator = MagicMock(spec=ExecutionOrchestrator)
    mock_reflection = MagicMock(spec=ReflectionEngine)
    mock_router = MagicMock(spec=ModelRouter)
    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_cost_gov = MagicMock(spec=CostGovernor)
    mock_event_bus = AsyncMock(spec=EventBusInterface)

    mock_cost_gov.check_budget_limits = AsyncMock()

    # Mock wave execution result
    from core.tools.dto import AggregatedWaveResult

    mock_wave_res = AggregatedWaveResult(
        wave_id=uuid4(),
        status="SUCCESS",
        combined_stdout="execution successfully routed via tool dispatcher",
        combined_stderr="",
        total_duration=0.5,
        artifacts={},
    )
    mock_orchestrator.execute_wave_new = AsyncMock(return_value=mock_wave_res)
    mock_orchestrator.event_bus = mock_event_bus

    # Mock MemoryService with search.search_hybrid path
    mock_record = MagicMock()
    mock_record.content = "System established in 2026."

    mock_search = MagicMock()
    mock_search.search_hybrid = AsyncMock(return_value=[mock_record])

    mock_memory = MagicMock()
    mock_memory.search = mock_search

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
        goal="Search memory for architecture information, run python code, echo message",
        budget=5.0,
        memory_service=mock_memory,
    )

    assert res["status"] == "SUCCESS"
    assert res["state"] == SessionState.COMPLETED
    assert res["waves_executed"] > 0
    assert res["memories_loaded"] == 1

    # Verify event transitions published
    assert mock_event_bus.publish.call_count >= 2


@pytest.mark.asyncio
async def test_engine_execute_goal_new_no_memory() -> None:
    """Verify execute_goal_new works without a memory service."""
    settings = Settings.load_settings()

    mock_orchestrator = MagicMock(spec=ExecutionOrchestrator)
    mock_reflection = MagicMock(spec=ReflectionEngine)
    mock_router = MagicMock(spec=ModelRouter)
    mock_prompt_builder = MagicMock(spec=PromptBuilder)
    mock_cost_gov = MagicMock(spec=CostGovernor)
    mock_event_bus = AsyncMock(spec=EventBusInterface)

    mock_cost_gov.check_budget_limits = AsyncMock()

    from core.tools.dto import AggregatedWaveResult

    mock_wave_res = AggregatedWaveResult(
        wave_id=uuid4(),
        status="SUCCESS",
        combined_stdout="done",
        combined_stderr="",
        total_duration=0.5,
        artifacts={},
    )
    mock_orchestrator.execute_wave_new = AsyncMock(return_value=mock_wave_res)
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
        goal="Run command: echo hello",
        budget=5.0,
    )

    assert res["status"] == "SUCCESS"
    assert res["memories_loaded"] == 0

"""
PHASE: 24
STATUS: TEST
SPECIFICATION:
    docs/84_PHASE_24_AUTONOMOUS_AGENT_SPECIFICATION.md

AUTHORITATIVE: NO
"""

from typing import List
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.reasoning.agent_loop import AgentLoop
from core.reasoning.decision_engine import DecisionEngine
from core.reasoning.dispatcher import ToolDispatcher
from core.reasoning.reflection import ReflectionEngine
from core.reasoning.task import (
    AgentTerminationReason,
    ExecutorType,
    Task,
    TaskType,
)
from core.tools.dto import ToolExecutionResult


def _ok_result() -> ToolExecutionResult:
    r = MagicMock(spec=ToolExecutionResult)
    r.status = "SUCCESS"
    r.exit_code = 0
    r.stdout = "ok output"
    r.stderr = ""
    r.error = ""
    r.artifacts = []
    return r


def _fail_result(stderr: str = "SyntaxError: bad code") -> ToolExecutionResult:
    r = MagicMock(spec=ToolExecutionResult)
    r.status = "FAILURE"
    r.exit_code = 1
    r.stdout = ""
    r.stderr = stderr
    r.error = ""
    r.artifacts = []
    return r


def _task(
    description: str = "do something", executor: ExecutorType = ExecutorType.PYTHON
) -> Task:
    return Task(
        goal_id=uuid4(),
        executor=executor,
        task_type=TaskType.SYSTEM,
        payload={"instruction": description, "description": description},
    )


def _make_loop(dispatcher_results: List[ToolExecutionResult]) -> AgentLoop:
    dispatcher = MagicMock(spec=ToolDispatcher)
    dispatcher.dispatch = AsyncMock(side_effect=dispatcher_results)
    return AgentLoop(
        dispatcher=dispatcher,
        reflection_engine=ReflectionEngine(),
        decision_engine=DecisionEngine(),
        max_iterations=10,
    )


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_single_successful_task(self) -> None:
        loop = _make_loop([_ok_result()])
        result = await loop.run([_task()])
        assert result.termination_reason == AgentTerminationReason.SUCCESS
        assert result.tasks_completed == 1
        assert result.tasks_failed == 0
        assert result.iterations_used == 1

    @pytest.mark.asyncio
    async def test_multiple_successful_tasks(self) -> None:
        loop = _make_loop([_ok_result(), _ok_result(), _ok_result()])
        result = await loop.run([_task(), _task(), _task()])
        assert result.termination_reason == AgentTerminationReason.SUCCESS
        assert result.tasks_completed == 3
        assert result.tasks_failed == 0

    @pytest.mark.asyncio
    async def test_single_failed_then_replan(self) -> None:
        """A SyntaxError should cause replan (insert repair task), not abort."""
        # First call fails, repair succeeds, retry succeeds
        loop = _make_loop([_fail_result(), _ok_result(), _ok_result()])
        result = await loop.run([_task()])
        # Should eventually succeed after repair
        assert result.tasks_completed >= 1

    @pytest.mark.asyncio
    async def test_budget_exceeded_triggers_abort(self) -> None:
        loop = _make_loop(
            [
                _fail_result("BUDGET exhausted for daily limit"),
            ]
        )
        result = await loop.run([_task()])
        assert result.termination_reason == AgentTerminationReason.FAILED
        assert result.tasks_failed >= 1

    @pytest.mark.asyncio
    async def test_permission_denied_triggers_abort(self) -> None:
        loop = _make_loop(
            [
                _fail_result(
                    "PermissionError: [Errno 13] Permission denied: '/etc/passwd'"
                ),
            ]
        )
        result = await loop.run([_task()])
        assert result.termination_reason == AgentTerminationReason.FAILED

    @pytest.mark.asyncio
    async def test_iteration_limit_stops_loop(self) -> None:
        """If every task fails and the queue keeps growing, iteration cap fires."""
        dispatcher = MagicMock(spec=ToolDispatcher)
        # Always return a recoverable failure (triggers replan endlessly)
        dispatcher.dispatch = AsyncMock(
            return_value=_fail_result("SyntaxError: looping failure")
        )
        loop = AgentLoop(
            dispatcher=dispatcher,
            reflection_engine=ReflectionEngine(),
            decision_engine=DecisionEngine(),
            max_iterations=3,  # Very small limit for this test
        )
        result = await loop.run([_task()])
        assert result.termination_reason == AgentTerminationReason.ITERATION_LIMIT
        assert result.iterations_used == 3

    @pytest.mark.asyncio
    async def test_memory_updates_on_success(self) -> None:
        loop = _make_loop([_ok_result()])
        result = await loop.run([_task()])
        assert len(result.memory_updates) >= 1
        assert result.memory_updates[0]["status"] == "success"
        assert result.memory_updates[0]["confidence"] >= 0.90
        assert result.memory_updates[0]["tentative"] is False

    @pytest.mark.asyncio
    async def test_memory_updates_on_failure_are_tentative(self) -> None:
        loop = _make_loop(
            [
                _fail_result("PermissionError: denied"),
            ]
        )
        result = await loop.run([_task()])
        assert any(m["tentative"] for m in result.memory_updates)

    @pytest.mark.asyncio
    async def test_final_outputs_collected(self) -> None:
        loop = _make_loop([_ok_result(), _ok_result()])
        result = await loop.run([_task(), _task()])
        assert len(result.final_outputs) == 2
        for out in result.final_outputs:
            assert "task_id" in out
            assert "stdout" in out

    @pytest.mark.asyncio
    async def test_empty_task_list_returns_success(self) -> None:
        loop = _make_loop([])
        result = await loop.run([])
        assert result.termination_reason == AgentTerminationReason.SUCCESS
        assert result.tasks_completed == 0
        assert result.iterations_used == 0

"""
PHASE: 40
STATUS: TEST
SPECIFICATION:
    Goal #4 — Autonomous Repair
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.reasoning.reflection import (
    FailureCategory,
    ReflectionEngine,
    RepairStrategy,
)
from core.reasoning.repair_engine import (
    RepairEngine,
    RepairOutcome,
    RepairPlan,
    RepairRecord,
)
from core.reasoning.task import ExecutorType, Task, TaskType
from core.tools.dto import ToolExecutionResult


# ── Helpers ─────────────────────────────────────────────────────────────────


_TEST_UUID = uuid4()


def _result(
    status: str = "SUCCESS",
    exit_code: int = 0,
    stderr: str = "",
    error: str = "",
) -> ToolExecutionResult:
    return ToolExecutionResult(
        task_id=_TEST_UUID,
        status=status,
        exit_code=exit_code,
        stderr=stderr,
        error=error,
        stdout="output" if status == "SUCCESS" else "",
    )


def _task(
    executor: ExecutorType = ExecutorType.PYTHON,
    payload: dict | None = None,
) -> Task:
    return Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=executor,
        task_type=TaskType.CODE,
        payload=payload or {"instruction": "run analysis"},
    )


def _mock_executor(success: bool = True) -> AsyncMock:
    executor = AsyncMock()
    executor.execute.return_value = _result(
        status="SUCCESS" if success else "ERROR",
        exit_code=0 if success else 1,
        stderr="" if success else "mock error",
        error="" if success else "mock error",
    )
    return executor


# ── Tests ───────────────────────────────────────────────────────────────────


class TestRepairEngineInit:
    def test_creates_with_defaults(self) -> None:
        engine = RepairEngine(reflection_engine=ReflectionEngine())
        assert engine.get_repair_history() == []
        assert engine.get_success_rate() == 0.0

    def test_creates_with_all_components(self) -> None:
        engine = RepairEngine(
            reflection_engine=ReflectionEngine(),
            tool_selector=MagicMock(),
            llm_runtime=MagicMock(),
        )
        assert engine._tool_selector is not None
        assert engine._llm_runtime is not None


class TestRepairEngineClassify:
    """Tests that RepairEngine correctly delegates classification to ReflectionEngine."""

    @pytest.mark.asyncio
    async def test_success_result_skips_repair(self) -> None:
        engine = RepairEngine(reflection_engine=ReflectionEngine())
        task = _task()
        result = _result()
        executors = {ExecutorType.PYTHON: _mock_executor()}

        outcome = await engine.attempt_repair(task, result, executors, {})
        assert outcome.result.status == "SUCCESS"
        assert outcome.attempts == 0

    @pytest.mark.asyncio
    async def test_unrecoverable_failure_aborts(self) -> None:
        engine = RepairEngine(reflection_engine=ReflectionEngine())
        task = _task()
        result = _result(
            status="FAILURE", exit_code=1,
            stderr="PermissionError: [Errno 13] Permission denied",
        )
        executors = {ExecutorType.PYTHON: _mock_executor()}

        outcome = await engine.attempt_repair(task, result, executors, {})
        assert outcome.attempts == 0
        assert outcome.result.status == "FAILURE"


class TestRepairPlanGeneration:
    @pytest.mark.asyncio
    async def test_generates_plan_for_missing_dep(self) -> None:
        engine = RepairEngine(reflection_engine=ReflectionEngine())
        task = _task()
        result = _result(
            status="FAILURE", exit_code=1,
            stderr="ModuleNotFoundError: No module named 'pandas'",
        )
        shell_executor = _mock_executor(success=True)
        executors = {
            ExecutorType.PYTHON: _mock_executor(success=False),
            ExecutorType.SHELL: shell_executor,
        }

        outcome = await engine.attempt_repair(task, result, executors, {})
        assert outcome.attempts > 0
        assert outcome.result.status == "SUCCESS"

    @pytest.mark.asyncio
    async def test_uses_cached_pattern(self) -> None:
        engine = RepairEngine(reflection_engine=ReflectionEngine())

        cached_strategy = RepairStrategy(
            strategy="Use cached repair",
            suggested_executor="shell",
            confidence=0.85,
        )
        engine._pattern_cache["ModuleNotFoundError: No module named 'pandas'"] = cached_strategy

        task = _task()
        result = _result(
            status="FAILURE", exit_code=1,
            stderr="ModuleNotFoundError: No module named 'pandas'",
        )
        shell_executor = _mock_executor(success=True)
        executors = {
            ExecutorType.PYTHON: _mock_executor(success=False),
            ExecutorType.SHELL: shell_executor,
        }

        outcome = await engine.attempt_repair(task, result, executors, {})
        assert outcome.result.status == "SUCCESS"
        assert outcome.strategy_used is not None


class TestMultiStageRetry:
    @pytest.mark.asyncio
    async def test_escalates_through_strategies(self) -> None:
        engine = RepairEngine(reflection_engine=ReflectionEngine())
        task = _task()
        result = _result(
            status="FAILURE", exit_code=1,
            stderr="SyntaxError: invalid syntax",
        )

        call_count = 0

        async def escalating_execute(t, c):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return _result(status="SUCCESS")
            return _result(status="ERROR", exit_code=1, stderr="still failing")

        python_exec = AsyncMock()
        python_exec.execute.side_effect = escalating_execute
        executors = {ExecutorType.PYTHON: python_exec}

        outcome = await engine.attempt_repair(task, result, executors, {})
        assert outcome.attempts >= 1

    @pytest.mark.asyncio
    async def test_all_strategies_fail_returns_last_error(self) -> None:
        engine = RepairEngine(reflection_engine=ReflectionEngine())
        task = _task()
        result = _result(
            status="FAILURE", exit_code=1,
            stderr="something totally unexpected happened",
        )
        failing_executor = _mock_executor(success=False)
        executors = {
            ExecutorType.PYTHON: failing_executor,
            ExecutorType.SHELL: _mock_executor(success=False),
        }

        outcome = await engine.attempt_repair(task, result, executors, {})
        assert outcome.result.status != "SUCCESS"
        assert outcome.strategy_used is None
        assert outcome.learned is False


class TestLearnFromFailures:
    @pytest.mark.asyncio
    async def test_learns_successful_repair(self) -> None:
        engine = RepairEngine(reflection_engine=ReflectionEngine())
        task = _task()
        result = _result(
            status="FAILURE", exit_code=1,
            stderr="ModuleNotFoundError: No module named 'requests'",
        )
        executors = {
            ExecutorType.PYTHON: _mock_executor(success=False),
            ExecutorType.SHELL: _mock_executor(success=True),
        }

        outcome = await engine.attempt_repair(task, result, executors, {})
        assert outcome.learned is True
        assert len(engine.get_repair_history()) == 1

        record = engine.get_repair_history()[0]
        assert record.success is True
        assert record.failure_category == FailureCategory.MISSING_DEPENDENCY

    @pytest.mark.asyncio
    async def test_category_stats_tracked(self) -> None:
        engine = RepairEngine(reflection_engine=ReflectionEngine())

        for stderr_msg in [
            "ModuleNotFoundError: No module named 'a'",
            "ModuleNotFoundError: No module named 'b'",
        ]:
            task = _task()
            result = _result(status="FAILURE", exit_code=1, stderr=stderr_msg)
            executors = {
                ExecutorType.PYTHON: _mock_executor(success=False),
                ExecutorType.SHELL: _mock_executor(success=True),
            }
            await engine.attempt_repair(task, result, executors, {})

        stats = engine.get_category_stats()
        assert "MISSING_DEPENDENCY" in stats
        assert stats["MISSING_DEPENDENCY"]["successes"] == 2

    def test_success_rate_calculation(self) -> None:
        engine = RepairEngine(reflection_engine=ReflectionEngine())
        engine._repair_history = [
            RepairRecord(
                failure_category=FailureCategory.SYNTAX_ERROR,
                error_signature="test",
                original_executor="python",
                repair_executor="python",
                strategy_used="retry",
                success=True,
            ),
            RepairRecord(
                failure_category=FailureCategory.UNKNOWN,
                error_signature="test2",
                original_executor="python",
                repair_executor="shell",
                strategy_used="fallback",
                success=False,
            ),
        ]
        assert engine.get_success_rate() == 0.5


class TestConfidenceUpdate:
    @pytest.mark.asyncio
    async def test_records_result_in_tool_selector(self) -> None:
        mock_selector = MagicMock()
        mock_selector.select_fallback = AsyncMock(return_value=None)
        mock_selector.record_result = MagicMock()

        engine = RepairEngine(
            reflection_engine=ReflectionEngine(),
            tool_selector=mock_selector,
        )
        task = _task()
        result = _result(
            status="FAILURE", exit_code=1,
            stderr="ModuleNotFoundError: No module named 'pandas'",
        )
        executors = {
            ExecutorType.PYTHON: _mock_executor(success=False),
            ExecutorType.SHELL: _mock_executor(success=True),
        }

        await engine.attempt_repair(task, result, executors, {})
        assert mock_selector.record_result.called


class TestWithLlmRuntime:
    @pytest.mark.asyncio
    async def test_llm_diagnosis_for_unknown_failures(self) -> None:
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Database connection pool exhausted due to leaked connections"
        mock_response.error = None
        mock_llm.generate = AsyncMock(return_value=mock_response)

        engine = RepairEngine(
            reflection_engine=ReflectionEngine(),
            llm_runtime=mock_llm,
        )
        task = _task()
        result = _result(
            status="FAILURE", exit_code=1,
            stderr="something totally unexpected happened",
        )
        executors = {
            ExecutorType.PYTHON: _mock_executor(success=True),
        }

        outcome = await engine.attempt_repair(task, result, executors, {})
        assert mock_llm.generate.called

    @pytest.mark.asyncio
    async def test_llm_failure_degrades_gracefully(self) -> None:
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(side_effect=Exception("LLM unavailable"))

        engine = RepairEngine(
            reflection_engine=ReflectionEngine(),
            llm_runtime=mock_llm,
        )
        task = _task()
        result = _result(
            status="FAILURE", exit_code=1,
            stderr="something totally unexpected happened",
        )
        executors = {ExecutorType.PYTHON: _mock_executor(success=True)}

        outcome = await engine.attempt_repair(task, result, executors, {})
        assert outcome.attempts > 0


class TestRepairRecordModel:
    def test_repair_record_fields(self) -> None:
        record = RepairRecord(
            failure_category=FailureCategory.TIMEOUT,
            error_signature="timed out after 30s",
            original_executor="python",
            repair_executor="shell",
            strategy_used="Increase timeout",
            success=True,
        )
        assert record.failure_category == FailureCategory.TIMEOUT
        assert record.success is True
        assert record.timestamp > 0

    def test_repair_plan_fields(self) -> None:
        plan = RepairPlan(
            root_cause="Missing dependency",
            is_recoverable=True,
            strategies=[
                RepairStrategy(
                    strategy="Install package",
                    suggested_executor="shell",
                    confidence=0.85,
                ),
            ],
        )
        assert plan.is_recoverable is True
        assert len(plan.strategies) == 1


class TestRepairOutcomeModel:
    def test_outcome_defaults(self) -> None:
        outcome = RepairOutcome(
            result=_result(),
        )
        assert outcome.attempts == 0
        assert outcome.learned is False
        assert outcome.strategy_used is None

"""Phase 25 — ExecutionJournal unit tests.

Validates:
    - Append-only: record_iteration stores correct fields
    - Export ordering: always iteration ASC (deterministic)
    - Export text: human-readable string output
    - No edit/delete API exists
    - Journal integration with AgentLoop
    - Empty journal produces empty export
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from core.reasoning.agent_loop import AgentLoop
from core.reasoning.decision_engine import DecisionEngine
from core.reasoning.dispatcher import ToolDispatcher
from core.reasoning.journal import ExecutionJournal, IterationRecord
from core.reasoning.reflection import ReflectionEngine
from core.reasoning.task import AgentTerminationReason, ExecutorType, Task
from core.tools.dto import ToolExecutionResult

# ── Journal Unit Tests ───────────────────────────────────────────────────────


class TestExecutionJournal:
    def test_empty_journal_export(self) -> None:
        """Empty journal returns empty list."""
        journal = ExecutionJournal()
        assert journal.export() == []
        assert journal.export_text() == ""
        assert len(journal) == 0

    def test_record_stores_fields(self) -> None:
        """Recorded iteration has all expected fields."""
        journal = ExecutionJournal()
        journal.record_iteration(
            iteration=1,
            goal_description="Navigate to login page",
            chosen_executor="BROWSER",
            reasoning="Login needed before report download.",
            output_summary="Navigated to /login",
            next_action="CONTINUE",
        )
        records = journal.export()
        assert len(records) == 1
        rec = records[0]
        assert rec.iteration == 1
        assert rec.goal_description == "Navigate to login page"
        assert rec.chosen_executor == "BROWSER"
        assert rec.reasoning == "Login needed before report download."
        assert rec.output_summary == "Navigated to /login"
        assert rec.next_action == "CONTINUE"
        assert rec.reflection_category is None
        assert rec.timestamp is not None

    def test_append_only_multiple_records(self) -> None:
        """Multiple records are all preserved."""
        journal = ExecutionJournal()
        for i in range(1, 6):
            journal.record_iteration(iteration=i, goal_description=f"Step {i}")
        assert len(journal) == 5
        records = journal.export()
        assert [r.iteration for r in records] == [1, 2, 3, 4, 5]

    def test_export_is_sorted_ascending(self) -> None:
        """Export is always sorted by iteration ASC even if recorded out of order."""
        journal = ExecutionJournal()
        journal.record_iteration(iteration=3, goal_description="Third")
        journal.record_iteration(iteration=1, goal_description="First")
        journal.record_iteration(iteration=2, goal_description="Second")
        records = journal.export()
        assert [r.iteration for r in records] == [1, 2, 3]
        assert records[0].goal_description == "First"
        assert records[2].goal_description == "Third"

    def test_export_text_readable(self) -> None:
        """export_text() produces a human-readable multi-line string."""
        journal = ExecutionJournal()
        journal.record_iteration(
            iteration=1,
            goal_description="Test goal",
            chosen_executor="PYTHON",
            reasoning="Because tests need to pass.",
            output_summary="All tests passed.",
            next_action="SUCCESS",
        )
        text = journal.export_text()
        assert "Iteration 1" in text
        assert "Test goal" in text
        assert "PYTHON" in text
        assert "SUCCESS" in text

    def test_export_text_includes_reflection_when_set(self) -> None:
        """Reflection category appears in text output when present."""
        journal = ExecutionJournal()
        journal.record_iteration(
            iteration=1,
            goal_description="Failing step",
            reflection_category="TIMEOUT",
            next_action="REPLAN",
        )
        text = journal.export_text()
        assert "TIMEOUT" in text
        assert "REPLAN" in text

    def test_no_edit_or_delete_api(self) -> None:
        """Verify that no edit/delete/update/remove methods exist."""
        journal = ExecutionJournal()
        assert not hasattr(journal, "edit")
        assert not hasattr(journal, "delete")
        assert not hasattr(journal, "update")
        assert not hasattr(journal, "remove")
        assert not hasattr(journal, "clear")

    def test_iteration_record_is_pydantic_model(self) -> None:
        """IterationRecord is a Pydantic BaseModel with model_dump()."""
        rec = IterationRecord(
            iteration=1,
            goal_description="Test",
            next_action="CONTINUE",
        )
        d = rec.model_dump()
        assert d["iteration"] == 1
        assert d["next_action"] == "CONTINUE"


# ── AgentLoop + Journal Integration ──────────────────────────────────────────


def _make_task(payload: Dict[str, Any] | None = None) -> Task:
    return Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.PYTHON,
        task_type="code",
        payload=payload
        or {"description": "Run python script", "instruction": "print('hello')"},
    )


@pytest.mark.asyncio
async def test_agent_loop_with_journal_records_iterations() -> None:
    """AgentLoop populates journal records when a journal is provided."""
    # Mock dispatcher that always succeeds
    dispatcher = ToolDispatcher()
    for ex_type, ex in dispatcher.executors.items():
        mock_exec = AsyncMock()
        mock_exec.execute = AsyncMock(
            return_value=ToolExecutionResult(
                task_id=uuid4(), status="SUCCESS", stdout="OK", exit_code=0
            )
        )
        dispatcher.executors[ex_type] = mock_exec

    journal = ExecutionJournal()
    loop = AgentLoop(
        dispatcher=dispatcher,
        reflection_engine=ReflectionEngine(),
        decision_engine=DecisionEngine(),
        journal=journal,
    )

    tasks = [_make_task(), _make_task()]
    result = await loop.run(tasks, {})

    assert result.termination_reason == AgentTerminationReason.SUCCESS
    assert len(result.journal) == 2
    assert result.journal[0]["iteration"] == 1
    assert result.journal[1]["iteration"] == 2
    assert len(journal) == 2


@pytest.mark.asyncio
async def test_agent_loop_without_journal_still_works() -> None:
    """AgentLoop works fine without a journal (backward compat)."""
    dispatcher = ToolDispatcher()
    for ex_type, ex in dispatcher.executors.items():
        mock_exec = AsyncMock()
        mock_exec.execute = AsyncMock(
            return_value=ToolExecutionResult(
                task_id=uuid4(), status="SUCCESS", stdout="OK", exit_code=0
            )
        )
        dispatcher.executors[ex_type] = mock_exec

    loop = AgentLoop(
        dispatcher=dispatcher,
        reflection_engine=ReflectionEngine(),
        decision_engine=DecisionEngine(),
        # No journal — backward compat
    )

    tasks = [_make_task()]
    result = await loop.run(tasks, {})

    assert result.termination_reason == AgentTerminationReason.SUCCESS
    assert result.journal == []


@pytest.mark.asyncio
async def test_agent_loop_journal_records_failure() -> None:
    """Journal records abort events on unrecoverable failure."""
    dispatcher = ToolDispatcher()
    for ex_type, ex in dispatcher.executors.items():
        mock_exec = AsyncMock()
        mock_exec.execute = AsyncMock(
            return_value=ToolExecutionResult(
                task_id=uuid4(),
                status="FAILURE",
                stderr="BUDGET limit exceeded",
                exit_code=1,
                error="BUDGET limit exceeded",
            )
        )
        dispatcher.executors[ex_type] = mock_exec

    journal = ExecutionJournal()
    loop = AgentLoop(
        dispatcher=dispatcher,
        reflection_engine=ReflectionEngine(),
        decision_engine=DecisionEngine(),
        journal=journal,
    )

    tasks = [_make_task()]
    result = await loop.run(tasks, {})

    assert result.termination_reason == AgentTerminationReason.FAILED
    assert len(result.journal) == 1
    assert result.journal[0]["next_action"] == "ABORT"

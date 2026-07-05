"""
PHASE: 24
STATUS: TEST
SPECIFICATION:
    docs/84_PHASE_24_AUTONOMOUS_AGENT_SPECIFICATION.md

AUTHORITATIVE: NO
"""

from unittest.mock import MagicMock

from core.reasoning.reflection import (
    FailureCategory,
    ReflectionEngine,
)
from core.tools.dto import ToolExecutionResult


def _result(
    status: str = "SUCCESS",
    exit_code: int = 0,
    stderr: str = "",
    error: str = "",
) -> ToolExecutionResult:
    r = MagicMock(spec=ToolExecutionResult)
    r.status = status
    r.exit_code = exit_code
    r.stderr = stderr
    r.error = error
    r.stdout = "output"
    r.artifacts = []
    return r


class TestReflectionEngine:
    def setup_method(self) -> None:
        self.engine = ReflectionEngine()

    def test_success_result_returns_success(self) -> None:
        out = self.engine.analyze(_result())
        assert out.success is True
        assert out.failure_category is None
        assert out.repair_strategy is None
        assert out.should_replan is False
        assert out.should_abort is False

    def test_module_not_found_classified_as_missing_dep(self) -> None:
        r = _result(
            status="FAILURE",
            exit_code=1,
            stderr="ModuleNotFoundError: No module named 'pandas'",
        )
        out = self.engine.analyze(r)
        assert out.success is False
        assert out.failure_category == FailureCategory.MISSING_DEPENDENCY
        assert out.should_replan is True
        assert out.should_abort is False
        assert out.repair_strategy is not None
        assert "shell" in (out.repair_strategy.suggested_executor or "")

    def test_syntax_error_classified(self) -> None:
        r = _result(status="FAILURE", exit_code=1, stderr="SyntaxError: invalid syntax")
        out = self.engine.analyze(r)
        assert out.failure_category == FailureCategory.SYNTAX_ERROR
        assert out.should_replan is True

    def test_permission_denied_triggers_abort(self) -> None:
        r = _result(
            status="FAILURE",
            exit_code=1,
            stderr="PermissionError: [Errno 13] Permission denied",
        )
        out = self.engine.analyze(r)
        assert out.failure_category == FailureCategory.PERMISSION_DENIED
        assert out.should_abort is True
        assert out.should_replan is False

    def test_budget_exceeded_triggers_abort(self) -> None:
        r = _result(
            status="FAILURE", exit_code=1, error="BUDGET exhausted for daily limit"
        )
        out = self.engine.analyze(r)
        assert out.failure_category == FailureCategory.BUDGET_EXCEEDED
        assert out.should_abort is True

    def test_timeout_classified(self) -> None:
        r = _result(
            status="FAILURE", exit_code=124, stderr="Command timed out after 30s"
        )
        out = self.engine.analyze(r)
        assert out.failure_category == FailureCategory.TIMEOUT
        assert out.should_replan is True

    def test_network_error_classified(self) -> None:
        r = _result(
            status="FAILURE", exit_code=1, stderr="Connection refused: localhost:8080"
        )
        out = self.engine.analyze(r)
        assert out.failure_category == FailureCategory.NETWORK_ERROR

    def test_unknown_failure_has_low_confidence(self) -> None:
        r = _result(
            status="FAILURE",
            exit_code=1,
            stderr="something totally unexpected happened",
        )
        out = self.engine.analyze(r)
        assert out.failure_category == FailureCategory.UNKNOWN
        assert out.repair_strategy is not None
        assert out.repair_strategy.confidence < 0.5

    def test_reflection_engine_never_executes_tools(self) -> None:
        """Architectural invariant: ReflectionEngine has no executor/dispatcher attr."""
        engine = ReflectionEngine()
        assert not hasattr(engine, "dispatcher")
        assert not hasattr(engine, "executor")
        assert not hasattr(engine, "tool")

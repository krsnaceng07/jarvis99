"""
PHASE: 19
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/governance/quality_gates_engine.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from unittest.mock import MagicMock, patch

from scripts.quality_gate import parse_coverage_from_output, run_pipeline


def test_parse_coverage_valid() -> None:
    output = "TOTAL     1000    100    90%"
    assert parse_coverage_from_output(output) == 90.0

    output_complex = "TOTAL  1234  123  87.5%\n"
    assert parse_coverage_from_output(output_complex) == 87.5

    output_invalid = "No percentage here"
    assert parse_coverage_from_output(output_invalid) is None


@patch("subprocess.run")
def test_run_pipeline_success(mock_run: MagicMock) -> None:
    # All stages return exit code 0
    mock_run.return_value = MagicMock(
        returncode=0, stdout="TOTAL  100  10  90%", stderr=""
    )

    exit_code, output = run_pipeline()
    assert exit_code == 0
    assert "QUALITY GATE PASSED" in output
    assert "90.0%" in output
    # Total 7 stages in loop + 1 combined test/coverage stage = 8 calls
    assert mock_run.call_count == 8


@patch("subprocess.run")
def test_run_pipeline_early_failure(mock_run: MagicMock) -> None:
    # First stage (Architecture Linter) fails
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Cycle detected")

    exit_code, output = run_pipeline()
    assert exit_code == 1
    assert "FAILED" in output
    assert "Architecture Linter" in output
    # Immediate stop: only 1 call is made
    assert mock_run.call_count == 1


@patch("subprocess.run")
def test_run_pipeline_tool_missing(mock_run: MagicMock) -> None:
    # Raise FileNotFoundError to mock missing tool
    mock_run.side_effect = FileNotFoundError()

    exit_code, output = run_pipeline()
    assert exit_code == 2
    assert "Tool Missing" in output
    assert mock_run.call_count == 1


@patch("subprocess.run")
def test_run_pipeline_internal_error(mock_run: MagicMock) -> None:
    # Raise generic exception to mock internal error
    mock_run.side_effect = Exception("Unexpected crash")

    exit_code, output = run_pipeline()
    assert exit_code == 8
    assert "Internal Error" in output
    assert mock_run.call_count == 1

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

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple


def parse_coverage_from_output(output: str) -> Optional[float]:
    """Parse the total coverage percentage from pytest-cov output."""
    # Look for a line like "TOTAL     1000    100    90%" or "TOTAL  1234  123  87.5%"
    match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)%", output)
    if match:
        return float(match.group(1))
    return None


def run_pipeline() -> Tuple[int, str]:
    """Run all quality gates in sequence. Returns (exit_code, output_summary)."""
    repo_dir = Path(__file__).resolve().parent.parent

    # Define stage commands
    stages = [
        ("Architecture Linter", [sys.executable, "-m", "scripts.architecture_linter"]),
        ("Dependency Graph Validator", [sys.executable, "-m", "scripts.dgv"]),
        ("Trace Checker", [sys.executable, "-m", "scripts.trace_check"]),
        ("Governance Checker", [sys.executable, "-m", "scripts.governance_check"]),
        ("Ruff Format", ["ruff", "format", "--check", "scripts", "tests"]),
        ("Ruff Lint", ["ruff", "check", "scripts", "tests"]),
        (
            "MyPy Check",
            [
                "mypy",
                "--strict",
                "scripts/architecture_linter.py",
                "scripts/dgv.py",
                "scripts/trace_check.py",
                "scripts/governance_check.py",
                "scripts/quality_gate.py",
                "tests/test_architecture_linter.py",
                "tests/test_dgv.py",
                "tests/test_trace_check.py",
                "tests/test_governance_check.py",
                "tests/test_quality_gate.py",
            ],
        ),
    ]

    console_log: List[str] = []

    for name, cmd in stages:
        try:
            res = subprocess.run(
                cmd,
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                console_log.append(
                    f"{name}\nFAILED\nReason: Command failed with exit code {res.returncode}\n{res.stderr or res.stdout}"
                )
                return 1, "\n".join(console_log)
            else:
                console_log.append(f"{name}\nPASS")
        except FileNotFoundError as err:
            console_log.append(f"{name}\nFAILED\nReason: Tool Missing - {err}")
            return 2, "\n".join(console_log)
        except Exception as err:
            console_log.append(f"{name}\nFAILED\nReason: Internal Error - {err}")
            return 8, "\n".join(console_log)

    # Stage 8: Tests and Stage 9: Coverage
    # Execute pytest-cov to get both test execution results and coverage
    try:
        test_cmd = ["pytest", "--cov=core", "--cov=api", "--cov-report=term-missing"]
        res = subprocess.run(
            test_cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        # Verify test execution status
        if res.returncode != 0:
            console_log.append(
                f"Pytest\nFAILED\nReason: Tests failed with exit code {res.returncode}\n{res.stderr or res.stdout}"
            )
            return 1, "\n".join(console_log)
        else:
            console_log.append("Pytest\nPASS")

        # Parse coverage percentage
        coverage_pct = parse_coverage_from_output(res.stdout)
        if coverage_pct is None:
            console_log.append(
                "Coverage\nFAILED\nReason: Could not parse coverage output"
            )
            return 1, "\n".join(console_log)

        if coverage_pct < 80.0:
            console_log.append(
                f"Coverage\n{coverage_pct}%\nFAILED\nReason: Coverage is below 80% threshold"
            )
            return 1, "\n".join(console_log)
        else:
            console_log.append(f"Coverage\n{coverage_pct}%\nPASS")

    except FileNotFoundError as err:
        console_log.append(f"Pytest/Coverage\nFAILED\nReason: Tool Missing - {err}")
        return 2, "\n".join(console_log)
    except Exception as err:
        console_log.append(f"Pytest/Coverage\nFAILED\nReason: Internal Error - {err}")
        return 8, "\n".join(console_log)

    console_log.append("QUALITY GATE PASSED")
    return 0, "\n".join(console_log)


def main() -> None:
    # Quick help
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python scripts/quality_gate.py")
        sys.exit(0)

    exit_code, summary = run_pipeline()
    print(summary)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

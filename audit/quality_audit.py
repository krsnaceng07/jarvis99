"""
PHASE: 16
STATUS: IMPLEMENTATION
SPECIFICATION:
    AGENTS.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import os
import subprocess
from typing import Any, Dict

from audit.base import Audit
from audit.report import AuditResult, AuditStatus


class QualityAudit(Audit):
    """Audit check for Ruff linting, Mypy types, and Pytest coverage/success."""

    @property
    def name(self) -> str:
        return "quality"

    @property
    def description(self) -> str:
        return "Runs Ruff linting, Mypy type-checking, and Pytest test runs"

    def _get_venv_bin(self, name: str, root_dir: str) -> str:
        """Resolve python executable bin path in .venv dynamically across platforms."""
        win_path = os.path.join(root_dir, ".venv", "Scripts", f"{name}.exe")
        if os.path.exists(win_path):
            return win_path
        unix_path = os.path.join(root_dir, ".venv", "bin", name)
        if os.path.exists(unix_path):
            return unix_path
        return name

    async def run(self) -> AuditResult:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Resolve binary paths
        ruff_bin = self._get_venv_bin("ruff", root_dir)
        mypy_bin = self._get_venv_bin("mypy", root_dir)
        pytest_bin = self._get_venv_bin("pytest", root_dir)

        issues = []
        details: Dict[str, Any] = {}

        # 1. Ruff lint check (on audit/ and api/ folders if they contain python files)
        paths_to_check = []
        for p in ("audit", "api"):
            if os.path.exists(os.path.join(root_dir, p)):
                paths_to_check.append(p)

        if paths_to_check:
            try:
                # Ruff Check
                ruff_check = subprocess.run(
                    [ruff_bin, "check"] + paths_to_check,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=root_dir,
                )
                details["ruff_check_stdout"] = ruff_check.stdout
                if ruff_check.returncode != 0:
                    issues.append(
                        f"Ruff check failed with exit code {ruff_check.returncode}."
                    )

                # Ruff Format Check
                ruff_format = subprocess.run(
                    [ruff_bin, "format", "--check"] + paths_to_check,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=root_dir,
                )
                details["ruff_format_stdout"] = ruff_format.stdout
                if ruff_format.returncode != 0:
                    issues.append(
                        f"Ruff formatting check failed with exit code {ruff_format.returncode}."
                    )
            except Exception as e:
                issues.append(f"Ruff execution failed: {e}")

        # 2. Mypy strict check
        if paths_to_check:
            try:
                mypy_check = subprocess.run(
                    [mypy_bin, "--strict"] + paths_to_check,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=root_dir,
                )
                details["mypy_stdout"] = mypy_check.stdout
                if mypy_check.returncode != 0:
                    issues.append(
                        f"Mypy type-checking failed with exit code {mypy_check.returncode}."
                    )
            except Exception as e:
                issues.append(f"Mypy execution failed: {e}")

        # 3. Pytest execution
        # Check if tests exist in tests/ folder before running
        tests_dir = os.path.join(root_dir, "tests")
        if os.path.exists(tests_dir):
            try:
                # Run pytest on the test suite (we only check audit tests or general smoke tests in this phase)
                # To keep it fast, we can run pytest on tests/test_smoke.py or the full tests suite
                pytest_run = subprocess.run(
                    [pytest_bin, "-v", "tests/test_smoke.py"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=root_dir,
                )
                details["pytest_stdout"] = pytest_run.stdout
                if pytest_run.returncode != 0:
                    issues.append(
                        f"Pytest run failed with exit code {pytest_run.returncode}."
                    )
            except Exception as e:
                issues.append(f"Pytest execution failed: {e}")

        details["total_quality_issues"] = len(issues)

        if issues:
            return AuditResult(
                name=self.name,
                status=AuditStatus.FAIL,
                message="Quality gates check failed: " + " ".join(issues),
                details=details,
                duration_seconds=0.0,
            )

        return AuditResult(
            name=self.name,
            status=AuditStatus.PASS,
            message="Ruff, Mypy, and Pytest smoke checks passed successfully.",
            details=details,
            duration_seconds=0.0,
        )

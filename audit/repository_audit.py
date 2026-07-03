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
import re
import subprocess
from typing import List, Set

from audit.base import Audit
from audit.report import AuditResult, AuditStatus


class RepositoryAudit(Audit):
    """Audit check for standardized headers and naming conventions."""

    @property
    def name(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "Enforces standardized code headers on modified files and validates naming conventions"

    def _get_modified_python_files(self, root_dir: str) -> Set[str]:
        """Identify modified or added python files using git, or fallback to scanning api/ and audit/ folders."""
        modified_files: Set[str] = set()

        # Try git status first
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                cwd=root_dir,
            )
            for line in res.stdout.splitlines():
                if not line.strip():
                    continue
                # Git status output starts with status codes (e.g. M, A, ??, AM)
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    file_path = parts[1].strip()
                    # Strip quotes if filename has spaces
                    if file_path.startswith('"') and file_path.endswith('"'):
                        file_path = file_path[1:-1]
                    if file_path.endswith(".py"):
                        abs_path = os.path.abspath(os.path.join(root_dir, file_path))
                        if os.path.exists(abs_path):
                            modified_files.add(abs_path)
        except Exception:
            # Fallback if git is not available or fails
            # Scan api/ and audit/ folders which are the active change zones
            for folder in ("api", "audit"):
                folder_path = os.path.join(root_dir, folder)
                if os.path.exists(folder_path):
                    for root, _, files in os.walk(folder_path):
                        for file in files:
                            if file.endswith(".py"):
                                modified_files.add(
                                    os.path.abspath(os.path.join(root, file))
                                )

        return modified_files

    def _check_header(self, file_path: str) -> str | None:
        """Verify that a python file has the required standardized code header.

        Returns error message string if missing, or None if valid.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return f"Failed to read file: {e}"

        # We look for the standardized block keywords inside the top-level docstring
        required_keywords = [
            "PHASE:",
            "STATUS: IMPLEMENTATION",
            "SPECIFICATION:",
            "IMPLEMENTATION PLAN:",
            "AUTHORITATIVE:",
            "DO NOT CHANGE CONTRACTS HERE.",
        ]

        # Read first 1000 characters to check header docstring
        header_sample = content[:1000]

        missing = []
        for kw in required_keywords:
            if kw not in header_sample:
                missing.append(kw)

        if missing:
            return f"Missing required header fields: {', '.join(missing)}"

        return None

    def _check_naming_conventions(self, root_dir: str) -> List[str]:
        """Validate naming conventions: python files and directories must use snake_case."""
        violations = []
        # snake_case pattern: lowercase letters, numbers, and underscores
        snake_case_pattern = re.compile(r"^[a-z0-9_]+$")

        # Exclude directories we don't own or standard ones
        exclude_dirs = {
            ".git",
            ".github",
            ".venv",
            "venv",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "__pycache__",
        }

        for root, dirs, files in os.walk(root_dir):
            # Prune directory search path
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            # Check subdirectories
            for d in dirs:
                if not snake_case_pattern.match(d):
                    violations.append(
                        f"Directory naming violation: '{d}' (should be snake_case)"
                    )

            # Check files (only python files in api/, core/, audit/, tests/)
            rel_root = os.path.relpath(root, root_dir)
            active_dirs = ("api", "core", "audit", "tests")
            if rel_root.startswith(active_dirs) or rel_root == ".":
                for file in files:
                    if file.endswith(".py") and file != "__init__.py":
                        name_without_ext = os.path.splitext(file)[0]
                        if not snake_case_pattern.match(name_without_ext):
                            violations.append(
                                f"File naming violation in '{rel_root}': '{file}' (should be snake_case.py)"
                            )

        return violations

    async def run(self) -> AuditResult:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        modified_files = self._get_modified_python_files(root_dir)
        header_violations = []

        # Validate headers on modified files in active zones (api/ and audit/)
        for file_path in modified_files:
            rel_path = os.path.relpath(file_path, root_dir)
            if not (rel_path.startswith("api") or rel_path.startswith("audit")):
                continue

            # Skip empty __init__.py files
            if (
                os.path.basename(file_path) == "__init__.py"
                and os.path.getsize(file_path) <= 100
            ):
                continue

            error = self._check_header(file_path)
            if error:
                header_violations.append(f"'{rel_path}': {error}")

        naming_violations = self._check_naming_conventions(root_dir)

        all_violations = header_violations + naming_violations

        details = {
            "modified_files_checked": [
                os.path.relpath(f, root_dir) for f in modified_files
            ],
            "header_violations": header_violations,
            "naming_violations": naming_violations,
            "total_violations": len(all_violations),
        }

        if all_violations:
            return AuditResult(
                name=self.name,
                status=AuditStatus.FAIL,
                message=f"Repository checks failed with {len(all_violations)} violation(s).",
                details=details,
                duration_seconds=0.0,
            )

        return AuditResult(
            name=self.name,
            status=AuditStatus.PASS,
            message="All modified file headers and naming conventions conform to standards.",
            details=details,
            duration_seconds=0.0,
        )

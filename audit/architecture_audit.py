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

import ast
import os
from typing import Dict, List, Set, Tuple

from audit.base import Audit
from audit.report import AuditResult, AuditStatus


class ArchitectureAudit(Audit):
    """Audit check for layering and circular imports."""

    @property
    def name(self) -> str:
        return "architecture"

    @property
    def description(self) -> str:
        return (
            "Checks layering rules (core -> api violations) and circular dependencies"
        )

    def _get_python_files(self, root_dir: str) -> List[Tuple[str, str]]:
        """Walk directory and return list of (file_path, module_name) for project python files.

        Excludes tests, .venv, audit, and alembic migration folders.
        """
        python_files = []
        exclude_dirs = {
            ".venv",
            "venv",
            "tests",
            "audit",
            "alembic",
            "__pycache__",
            ".git",
        }

        for root, dirs, files in os.walk(root_dir):
            # Prune directory search path
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    # Convert absolute path to dot-separated module path relative to root_dir
                    rel_path = os.path.relpath(full_path, root_dir)
                    module_name = os.path.splitext(rel_path)[0].replace(os.sep, ".")
                    python_files.append((full_path, module_name))

        return python_files

    def _parse_imports(self, file_path: str, current_module: str) -> Set[str]:
        """Statically extract absolute project imports (starting with core or api) using AST."""
        imported_modules: Set[str] = set()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=file_path)
        except Exception:
            # If a file is un-parseable, other audits will catch syntax, skip here
            return imported_modules

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name.startswith("core") or name.startswith("api"):
                        imported_modules.add(name)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    # Resolve relative imports
                    if node.level > 0:
                        parts = current_module.split(".")
                        # Go up 'level' times
                        base = ".".join(parts[: -node.level])
                        resolved_module = (
                            f"{base}.{node.module}" if base else node.module
                        )
                    else:
                        resolved_module = node.module

                    if resolved_module.startswith("core") or resolved_module.startswith(
                        "api"
                    ):
                        imported_modules.add(resolved_module)
                        # Also track the imported names in case they are modules themselves
                        for alias in node.names:
                            imported_modules.add(f"{resolved_module}.{alias.name}")

        return imported_modules

    def _find_cycle(self, graph: Dict[str, Set[str]]) -> List[str] | None:
        """DFS-based cycle detection. Returns first cycle path found, or None."""
        visited: Set[str] = set()
        stack: List[str] = []
        in_stack: Set[str] = set()

        def dfs(node: str) -> List[str] | None:
            visited.add(node)
            stack.append(node)
            in_stack.add(node)

            for neighbor in graph.get(node, []):
                # We only trace edges that exist in our module nodes
                if neighbor in graph:
                    if neighbor in in_stack:
                        # Found a cycle, return the path
                        idx = stack.index(neighbor)
                        return stack[idx:] + [neighbor]
                    if neighbor not in visited:
                        cycle = dfs(neighbor)
                        if cycle:
                            return cycle

            stack.pop()
            in_stack.remove(node)
            return None

        for node in graph:
            if node not in visited:
                cycle = dfs(node)
                if cycle:
                    return cycle

        return None

    async def run(self) -> AuditResult:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        python_files = self._get_python_files(root_dir)

        graph: Dict[str, Set[str]] = {}
        layer_violations: List[str] = []

        # Step 1: Build dependency graph and check layering rule (core never imports api)
        for file_path, module_name in python_files:
            imports = self._parse_imports(file_path, module_name)
            graph[module_name] = imports

            # Core to API violation check
            if module_name.startswith("core"):
                for imp in imports:
                    if imp.startswith("api"):
                        layer_violations.append(
                            f"Layer Violation: module '{module_name}' imports '{imp}' from higher api layer"
                        )

        # Step 2: Cycle detection
        cycle_path = self._find_cycle(graph)

        details = {
            "total_modules_scanned": len(python_files),
            "layer_violations": layer_violations,
            "circular_dependency": " -> ".join(cycle_path) if cycle_path else None,
        }

        # Step 3: Determine audit outcome
        if layer_violations or cycle_path:
            messages = []
            if layer_violations:
                messages.append(f"{len(layer_violations)} layer violation(s) detected.")
            if cycle_path:
                messages.append(
                    f"Circular dependency cycle detected: {' -> '.join(cycle_path)}"
                )

            return AuditResult(
                name=self.name,
                status=AuditStatus.FAIL,
                message="; ".join(messages),
                details=details,
                duration_seconds=0.0,
            )

        return AuditResult(
            name=self.name,
            status=AuditStatus.PASS,
            message="No layer violations or circular dependencies found.",
            details=details,
            duration_seconds=0.0,
        )

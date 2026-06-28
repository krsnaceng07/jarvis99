"""JARVIS OS - Workflow Validator.

Implements structural validation, tool discovery checking, compatibility validation,
DAG dependency cycle resolution, and parameter binding syntax parsing.
"""

import re
from typing import Any, Dict, List, Set

from core.exceptions import JarvisSkillError
from core.tools.registry import ToolRegistry
from core.tools.workflow_dto import WorkflowPlan, WorkflowStep

VAR_PATTERN = re.compile(
    r"^\{\{\s*steps\.([a-zA-Z0-9_-]+)\.output\.([a-zA-Z0-9_-]+)\s*\}\}$"
)
ANY_TEMPLATE_PATTERN = re.compile(r"\{\{.*?\}\}")


class WorkflowValidator:
    """Validator class ensuring workflows are correct, cycle-free, and safe before compilation."""

    def __init__(self, registry: ToolRegistry) -> None:
        """Initialize validator with a ToolRegistry.

        Args:
            registry: ToolRegistry instance containing registered skills.
        """
        self.registry = registry

    def validate(self, plan: WorkflowPlan) -> None:
        """Validate a raw WorkflowPlan schema and dependencies.

        Args:
            plan: The WorkflowPlan configuration.

        Raises:
            ValueError: If schema, uniqueness, DAG cycles, timeouts, or variable reference syntax checks fail.
            JarvisSkillError: If a referenced tool is missing or incompatible.
        """
        if not plan.name.strip():
            raise ValueError("Workflow name cannot be empty.")

        if not plan.steps:
            raise ValueError("Workflow must contain at least one step.")

        step_names: Set[str] = set()

        for step in plan.steps:
            # 1. Schema check
            if not step.name.strip():
                raise ValueError("Step name cannot be empty.")

            # 2. Duplicate step name detection
            if step.name in step_names:
                raise ValueError(
                    f"Duplicate step name '{step.name}' detected in workflow."
                )
            step_names.add(step.name)

            # 3. Timeout validation
            if step.timeout <= 0:
                raise ValueError(
                    f"Step '{step.name}' must have a positive timeout. Found: {step.timeout}."
                )

            # 4. Missing tool detection and compatibility validation
            manifest = self.registry.get_skill(step.tool_name)
            if not manifest:
                raise JarvisSkillError(
                    code="WORKFLOW_TOOL_MISSING",
                    message=f"Step '{step.name}' references missing or unregistered tool '{step.tool_name}'.",
                )

            # 5. Compatibility checking
            if float(manifest.jarvis_api_version) > float(
                self.registry.SYSTEM_API_VERSION
            ):
                raise JarvisSkillError(
                    code="WORKFLOW_API_INCOMPATIBLE",
                    message=(
                        f"Tool '{step.tool_name}' requires API version {manifest.jarvis_api_version}, "
                        f"which is newer than system API version {self.registry.SYSTEM_API_VERSION}."
                    ),
                )

            # 6. Variable reference syntax checking
            self._validate_args_syntax(step.name, step.arguments)

        # 7. DAG dependency checks & cycle detection
        self._check_cycles(plan.steps)

    def _validate_args_syntax(self, step_name: str, arguments: Dict[str, Any]) -> None:
        """Recursively scan arguments structure validating template interpolation references."""

        def _traverse(val: Any) -> None:
            if isinstance(val, str):
                templates = ANY_TEMPLATE_PATTERN.findall(val)
                for t in templates:
                    match = VAR_PATTERN.match(t)
                    if not match:
                        raise ValueError(
                            f"Step '{step_name}' has invalid variable reference '{t}'. "
                            "Must strictly match the format '{{steps.step_name.output.variable_name}}'."
                        )
            elif isinstance(val, dict):
                for v in val.values():
                    _traverse(v)
            elif isinstance(val, list):
                for item in val:
                    _traverse(item)

        _traverse(arguments)

    def _check_cycles(self, steps: List[WorkflowStep]) -> None:
        """Build dependency graph and detect cyclic relations."""
        step_names = {s.name for s in steps}
        adj: Dict[str, List[str]] = {s.name: [] for s in steps}

        for s in steps:
            for dep in s.dependencies:
                if dep not in step_names:
                    raise ValueError(
                        f"Step '{s.name}' depends on non-existent step '{dep}'."
                    )
                adj[s.name].append(dep)

        visited: Dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited

        def dfs(u: str) -> None:
            visited[u] = 1
            for v in adj[u]:
                if visited.get(v, 0) == 1:
                    raise ValueError(
                        f"Circular dependency cycle detected involving step '{u}' and step '{v}'."
                    )
                elif visited.get(v, 0) == 0:
                    dfs(v)
            visited[u] = 2

        for name in step_names:
            if visited.get(name, 0) == 0:
                dfs(name)

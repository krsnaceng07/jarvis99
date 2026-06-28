"""JARVIS OS - Workflow Compiler.

Implements topological sorting for wave generation, dynamic variable dependency checks,
circular reference checks, and nested variable lookup depth enforcement.
"""

from typing import Any, Dict, List, Set

from core.tools.validator import ANY_TEMPLATE_PATTERN, VAR_PATTERN
from core.tools.workflow_dto import CompiledWorkflow, WorkflowPlan, WorkflowStep


class WorkflowCompiler:
    """Compiles WorkflowPlans into immutable CompiledWorkflows with verified reference DAGs."""

    def compile(self, plan: WorkflowPlan) -> CompiledWorkflow:
        """Compile a validated WorkflowPlan into an immutable CompiledWorkflow.

        Args:
            plan: The verified WorkflowPlan.

        Returns:
            The CompiledWorkflow DTO.

        Raises:
            ValueError: If reference existence, circular reference, depth limit,
                        or dependency sorting checks fail.
        """
        steps = plan.steps
        steps_map = {s.name: s for s in steps}

        # 1. Topological Wave Sort
        waves = self._generate_waves(steps)

        # 2. Map steps to their wave indices
        step_wave_indices: Dict[str, int] = {}
        for wave_idx, wave in enumerate(waves):
            for step in wave:
                step_wave_indices[step.name] = wave_idx

        # 3. Variable Reference & Nesting Depth Validation
        for step in steps:
            referenced_steps = self._extract_references(step.arguments)

            for ref in referenced_steps:
                # Existence check
                if ref not in steps_map:
                    raise ValueError(
                        f"Step '{step.name}' references variable from non-existent step '{ref}'."
                    )

                # Execution order order check: ref step must execute in an earlier wave
                ref_wave = step_wave_indices[ref]
                curr_wave = step_wave_indices[step.name]
                if ref_wave >= curr_wave:
                    raise ValueError(
                        f"Step '{step.name}' references future step '{ref}' "
                        f"(Step '{step.name}' wave: {curr_wave}, Step '{ref}' wave: {ref_wave})."
                    )

            # Circular reference & depth check
            self._verify_lookup_depth(step.name, steps_map)

        return CompiledWorkflow(
            workflow_id=plan.workflow_id,
            version=plan.version,
            waves=waves,
        )

    def _generate_waves(self, steps: List[WorkflowStep]) -> List[List[WorkflowStep]]:
        """Sort steps topologically into parallel wave execution layers (Kahn's algorithm)."""
        in_degree = {s.name: 0 for s in steps}
        adj: Dict[str, List[str]] = {s.name: [] for s in steps}
        step_map = {s.name: s for s in steps}

        for s in steps:
            for dep in s.dependencies:
                if dep not in in_degree:
                    raise ValueError(
                        f"Step '{s.name}' depends on non-existent step '{dep}'."
                    )
                adj[dep].append(s.name)
                in_degree[s.name] += 1

        queue = [name for name, deg in in_degree.items() if deg == 0]
        waves: List[List[WorkflowStep]] = []

        while queue:
            current_wave: List[WorkflowStep] = []
            next_queue: List[str] = []
            for name in queue:
                current_wave.append(step_map[name])
                for neighbor in adj[name]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
            waves.append(current_wave)
            queue = next_queue

        flat_sorted = [s for wave in waves for s in wave]
        if len(flat_sorted) < len(steps):
            raise ValueError(
                "Circular dependency detected during topological sorting compilation."
            )

        return waves

    def _extract_references(self, arguments: Any) -> Set[str]:
        """Extract all step name references from template variables in step arguments."""
        refs: Set[str] = set()

        def _traverse(val: Any) -> None:
            if isinstance(val, str):
                templates = ANY_TEMPLATE_PATTERN.findall(val)
                for t in templates:
                    match = VAR_PATTERN.match(t)
                    if match:
                        refs.add(match.group(1))
            elif isinstance(val, dict):
                for v in val.values():
                    _traverse(v)
            elif isinstance(val, list):
                for item in val:
                    _traverse(item)

        _traverse(arguments)
        return refs

    def _verify_lookup_depth(
        self, start_step: str, steps_map: Dict[str, WorkflowStep]
    ) -> None:
        """Trace variables chain recursively to enforce nesting depth limit of 3."""

        def _get_depth(name: str, visited: Set[str]) -> int:
            if name in visited:
                raise ValueError(
                    f"Circular variable reference chain detected involving step '{name}'."
                )
            visited.add(name)

            referenced_steps = self._extract_references(steps_map[name].arguments)
            if not referenced_steps:
                return 1

            max_sub_depth = 0
            for ref in referenced_steps:
                max_sub_depth = max(max_sub_depth, _get_depth(ref, set(visited)))

            total_depth = max_sub_depth + 1
            if total_depth > 3:
                raise ValueError(
                    f"Variable nested lookup depth limit of 3 exceeded for step '{name}' (depth: {total_depth})."
                )
            return total_depth

        _get_depth(start_step, set())

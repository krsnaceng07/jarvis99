"""JARVIS OS - Task Dependency Resolver.

Builds a Directed Acyclic Graph (DAG) of WaveTasks, checks for circular dependencies,
and resolves execution layers of independent concurrent steps.
"""

from typing import List, Set
from uuid import UUID

from core.exceptions import JarvisSystemError
from core.tools.dto import WaveTask


class DependencyResolver:
    """DAG scheduler sorting tasks by parent dependencies into executable concurrent layers."""

    def resolve_execution_layers(self, tasks: List[WaveTask]) -> List[List[WaveTask]]:
        """Sort tasks topological-style into layers that can be executed concurrently.

        Args:
            tasks: List of tasks in the wave.

        Returns:
            A list of lists, where each sub-list contains WaveTasks that can be run in parallel.

        Raises:
            JarvisSystemError: If a cycle is detected or dependency refers to non-existent task.
        """
        if not tasks:
            return []

        # Maps task_id to WaveTask DTO
        task_map = {t.task_id: t for t in tasks}

        # Verify all dependencies actually exist in the wave
        for t in tasks:
            for dep in t.dependencies:
                if dep not in task_map:
                    raise JarvisSystemError(
                        code="ORCH_001",
                        message=f"Task '{t.task_id}' depends on missing task '{dep}' in the same wave.",
                    )

        layers: List[List[WaveTask]] = []
        resolved: Set[UUID] = set()
        unresolved = list(tasks)

        while unresolved:
            current_layer: List[WaveTask] = []
            for t in unresolved:
                # A task is ready if all its dependencies are already resolved
                if all(dep in resolved for dep in t.dependencies):
                    current_layer.append(t)

            if not current_layer:
                # Cycle detected
                cycle_details = [str(t.task_id) for t in unresolved]
                raise JarvisSystemError(
                    code="ORCH_002",
                    message=f"Circular dependency detected among tasks: {', '.join(cycle_details)}",
                )

            layers.append(current_layer)
            for t in current_layer:
                resolved.add(t.task_id)
                unresolved.remove(t)

        return layers

"""
PHASE: 21
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 21 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

from typing import List, Set
from uuid import UUID

from core.reasoning.dependency_graph import DependencyBuilder
from core.reasoning.task import ExecutorType


class ExecutionScheduler:
    """Orchestrates topological sorting of tasks into wave-based execution groups.

    Enforces parallel execution limits and resolves shared resource conflicts (e.g. BROWSER mutex).
    """

    def __init__(self, builder: DependencyBuilder) -> None:
        self.builder = builder
        self.tasks = builder.tasks
        self.task_map = builder.task_map
        self.adj_list = builder.adj_list

    def schedule_waves(self) -> List[List[UUID]]:
        """Group tasks into sequential execution waves.

        Rules:
        1. Topological sort (dependencies must execute in prior waves).
        2. Maximum of 3 parallel tasks per wave.
        3. Resource mutex: Only one BROWSER or HUMAN executor task allowed per wave.
        """
        # Make a copy of in-degrees to mutate during topological traversal
        in_degrees = dict(self.builder.in_degree)
        scheduled: Set[UUID] = set()
        waves: List[List[UUID]] = []

        while len(scheduled) < len(self.tasks):
            # 1. Identify all candidate tasks ready to run (in_degree == 0 and not yet scheduled)
            candidates = [t_id for t_id, deg in in_degrees.items() if deg == 0 and t_id not in scheduled]

            if not candidates:
                # Cycle or unresolvable dependencies (should be caught by builder.validate_dag)
                break

            # 2. Build the current wave, respecting limits and resource conflicts
            current_wave: List[UUID] = []
            active_resources: Set[str] = set()

            for t_id in candidates:
                if len(current_wave) >= 3:
                    break  # Wave parallel limit

                task = self.task_map[t_id]
                resource_key = None
                if task.executor in (ExecutorType.BROWSER, ExecutorType.HUMAN):
                    resource_key = task.executor.value
                elif task.payload.get("resource"):
                    resource_key = str(task.payload["resource"])

                if resource_key and resource_key in active_resources:
                    continue  # Mutex conflict; delay execution to next wave

                # Accept task in current wave
                current_wave.append(t_id)
                if resource_key:
                    active_resources.add(resource_key)

            # 3. Commit wave, decrement neighbor in-degrees, and mark scheduled
            waves.append(current_wave)
            for t_id in current_wave:
                scheduled.add(t_id)
                # Decrement neighbor degrees
                for neighbor in self.adj_list[t_id]:
                    if neighbor in in_degrees:
                        in_degrees[neighbor] -= 1

        return waves

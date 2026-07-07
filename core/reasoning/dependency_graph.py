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

from typing import Dict, List, Set
from uuid import UUID

from core.exceptions import JarvisSystemError
from core.reasoning.task import Task


class DependencyBuilder:
    """Constructs and validates the Task dependency Directed Acyclic Graph (DAG)."""

    def __init__(self, tasks: List[Task]) -> None:
        self.tasks = tasks
        self.task_map: Dict[UUID, Task] = {t.id: t for t in tasks}
        self.adj_list: Dict[UUID, Set[UUID]] = {t.id: set() for t in tasks}
        self.in_degree: Dict[UUID, int] = {t.id: 0 for t in tasks}

        self._build_graph()

    def _build_graph(self) -> None:
        """Construct the adjacency list and compute task in-degrees."""
        for task in self.tasks:
            for dep_id in task.dependencies:
                if dep_id in self.task_map:
                    # dep_id -> task.id is a directed dependency edge
                    self.adj_list[dep_id].add(task.id)
                    self.in_degree[task.id] += 1

    def validate_dag(self) -> None:
        """Validate that the dependency graph is a valid DAG without cycles.

        Raises:
            JarvisSystemError if a cycle or invalid dependency is detected.
        """
        # 1. Check for missing dependencies
        missing_deps = self.get_missing_dependencies()
        if missing_deps:
            raise JarvisSystemError(
                code="PLANNER_002",
                message=f"Plan contains missing task dependencies: {missing_deps}",
            )

        # 2. Cycle detection using DFS node state coloring
        # Node states: 0 = unvisited, 1 = visiting, 2 = visited
        visited: Dict[UUID, int] = {t.id: 0 for t in self.tasks}

        def dfs(node_id: UUID) -> bool:
            visited[node_id] = 1  # visiting
            for neighbor in self.adj_list[node_id]:
                if visited[neighbor] == 1:
                    return True  # cycle found
                if visited[neighbor] == 0:
                    if dfs(neighbor):
                        return True
            visited[node_id] = 2  # visited
            return False

        for task in self.tasks:
            if visited[task.id] == 0:
                if dfs(task.id):
                    raise JarvisSystemError(
                        code="PLANNER_003",
                        message="Dependency cycle detected in the execution plan.",
                    )

    def get_missing_dependencies(self) -> Set[UUID]:
        """Identify dependency IDs referenced by tasks that do not exist in the task list."""
        missing = set()
        for task in self.tasks:
            for dep_id in task.dependencies:
                if dep_id not in self.task_map:
                    missing.add(dep_id)
        return missing

    def get_orphan_tasks(self) -> Set[UUID]:
        """Find orphan tasks (tasks that have in-degree 0 and no children/out-degree 0).

        Excludes single-task plans.
        """
        if len(self.tasks) <= 1:
            return set()

        orphans = set()
        for t_id in self.adj_list:
            # An orphan task has no dependencies (in-degree 0) AND has no outgoing connections (out-degree 0)
            if self.in_degree[t_id] == 0 and len(self.adj_list[t_id]) == 0:
                orphans.add(t_id)
        return orphans

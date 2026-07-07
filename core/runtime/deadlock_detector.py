"""
PHASE: 41
STATUS: IMPLEMENTATION
SPECIFICATION:
    Goal #5 — Autonomous Multi-Agent Collaboration

Architecture:
    DeadlockDetector monitors lock chains and task dependency graphs
    for cycles. When a cycle is detected, it identifies the victim
    (lowest-priority agent) and forcefully releases its locks to
    break the deadlock.
    Uses existing MemoryLock for lock state inspection and
    AgentSupervisor for agent termination/reassignment.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DeadlockInfo(BaseModel):
    """Information about a detected deadlock cycle."""

    cycle: List[str] = Field(
        ..., description="Ordered list of resource keys forming the cycle.",
    )
    agents_involved: List[str] = Field(
        default_factory=list,
        description="Agent/owner IDs participating in the deadlock.",
    )
    victim: str = Field(
        default="", description="Agent selected for lock release to break deadlock.",
    )
    timestamp: float = Field(default_factory=time.time)
    resolved: bool = False


class WaitForEdge(BaseModel):
    """An edge in the wait-for graph: agent A waits for agent B."""

    waiter: str
    holder: str
    resource: str


class DeadlockDetector:
    """Detects and resolves deadlock cycles in agent lock chains.

    Detection algorithm:
        1. Build a wait-for graph from lock ownership and pending requests
        2. Run DFS cycle detection on the graph
        3. If cycle found → select victim → release victim's locks

    Integrates with:
        MemoryLock → lock state inspection
        AgentSupervisor → agent termination on deadlock
    """

    def __init__(
        self,
        lock_manager: Optional[Any] = None,
        supervisor: Optional[Any] = None,
    ) -> None:
        self._lock_manager = lock_manager
        self._supervisor = supervisor
        self._wait_for_edges: List[WaitForEdge] = []
        self._deadlock_history: List[DeadlockInfo] = []

    def register_wait(
        self,
        waiter: str,
        holder: str,
        resource: str,
    ) -> None:
        """Register that an agent is waiting for a lock held by another agent."""
        edge = WaitForEdge(waiter=waiter, holder=holder, resource=resource)
        if not any(
            e.waiter == waiter and e.holder == holder and e.resource == resource
            for e in self._wait_for_edges
        ):
            self._wait_for_edges.append(edge)

    def clear_wait(self, waiter: str, resource: str) -> None:
        """Remove a wait edge when the lock is acquired or request cancelled."""
        self._wait_for_edges = [
            e for e in self._wait_for_edges
            if not (e.waiter == waiter and e.resource == resource)
        ]

    def clear_agent(self, agent_id: str) -> None:
        """Remove all wait edges involving an agent (on termination)."""
        self._wait_for_edges = [
            e for e in self._wait_for_edges
            if e.waiter != agent_id and e.holder != agent_id
        ]

    def detect_cycles(self) -> List[DeadlockInfo]:
        """Run cycle detection on the current wait-for graph."""
        graph: Dict[str, List[str]] = {}
        edge_resources: Dict[Tuple[str, str], str] = {}

        for edge in self._wait_for_edges:
            if edge.waiter not in graph:
                graph[edge.waiter] = []
            graph[edge.waiter].append(edge.holder)
            edge_resources[(edge.waiter, edge.holder)] = edge.resource

        cycles = self._find_cycles(graph)
        deadlocks: List[DeadlockInfo] = []

        for cycle in cycles:
            resources = []
            for i in range(len(cycle)):
                waiter = cycle[i]
                holder = cycle[(i + 1) % len(cycle)]
                res = edge_resources.get((waiter, holder), "unknown")
                resources.append(res)

            victim = self._select_victim(cycle)

            info = DeadlockInfo(
                cycle=resources,
                agents_involved=cycle,
                victim=victim,
            )
            deadlocks.append(info)
            self._deadlock_history.append(info)

            logger.warning(
                "Deadlock detected: %s (victim: %s)",
                " → ".join(cycle + [cycle[0]]),
                victim,
            )

        return deadlocks

    async def detect_and_resolve(self) -> List[DeadlockInfo]:
        """Detect deadlocks and automatically resolve them."""
        deadlocks = self.detect_cycles()

        for dl in deadlocks:
            await self._resolve_deadlock(dl)
            dl.resolved = True

        return deadlocks

    async def _resolve_deadlock(self, deadlock: DeadlockInfo) -> None:
        """Break a deadlock by releasing the victim's locks."""
        victim = deadlock.victim
        if not victim:
            return

        if self._lock_manager is not None:
            for resource in deadlock.cycle:
                try:
                    released = await self._lock_manager.release(resource, victim)
                    if released:
                        logger.info(
                            "Released lock '%s' from victim '%s' to break deadlock.",
                            resource, victim,
                        )
                except Exception as e:
                    logger.debug("Failed to release lock %s: %s", resource, e)

        self.clear_agent(victim)

        if self._supervisor is not None:
            try:
                victim_uuid = UUID(victim)
                await self._supervisor.handle_agent_failure(
                    victim_uuid,
                    error=f"Deadlock victim: locks released for cycle {deadlock.cycle}",
                )
            except (ValueError, Exception) as e:
                logger.debug("Supervisor notification failed: %s", e)

    @staticmethod
    def _find_cycles(graph: Dict[str, List[str]]) -> List[List[str]]:
        """Find all cycles in a directed graph using DFS."""
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycles: List[List[str]] = []
        path: List[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:]
                    if cycle not in cycles:
                        cycles.append(list(cycle))

            path.pop()
            rec_stack.discard(node)

        for node in graph:
            if node not in visited:
                dfs(node)

        return cycles

    @staticmethod
    def _select_victim(cycle: List[str]) -> str:
        """Select the best victim to break a deadlock.

        Strategy: pick the last agent in the cycle (least likely to be
        critical). In production, this could use priority/role info.
        """
        if not cycle:
            return ""
        return cycle[-1]

    def get_deadlock_history(self) -> List[DeadlockInfo]:
        """Return all detected deadlocks for inspection."""
        return list(self._deadlock_history)

    def get_active_waits(self) -> List[WaitForEdge]:
        """Return currently active wait-for edges."""
        return list(self._wait_for_edges)

    def build_wait_for_graph_from_locks(self) -> None:
        """Rebuild wait-for edges from the lock manager's internal state.

        Inspects MemoryLock._locks to find ownership conflicts.
        Only works with MemoryLock (not RedisLock).
        """
        if self._lock_manager is None:
            return

        locks = getattr(self._lock_manager, "_locks", None)
        if locks is None or not isinstance(locks, dict):
            return

        owners: Dict[str, str] = dict(locks)
        for edge in self._wait_for_edges:
            actual_holder = owners.get(edge.resource)
            if actual_holder and actual_holder != edge.holder:
                edge.holder = actual_holder

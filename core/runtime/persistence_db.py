"""JARVIS OS - Swarm Database Persistence Adapter.

Implements the SwarmPersistence interface backed by SQLAlchemy.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import JarvisAgentError
from core.memory.database import db_manager
from core.runtime.dto import SwarmSnapshot, SwarmTask
from core.runtime.persistence import SwarmPersistence
from core.runtime.persistence_models import (
    AgentLoopJournalModel,
    SwarmAgentModel,
    SwarmMessageModel,
    SwarmSnapshotModel,
    SwarmTaskModel,
)

logger = logging.getLogger("jarvis.core.runtime.persistence_db")


class DbSwarmPersistence(SwarmPersistence):
    """Database persistence engine for swarm tasks and telemetry snapshots."""

    def __init__(self, session_factory: Any = None) -> None:
        """Initialize DbSwarmPersistence.

        Args:
            session_factory: Optional custom session factory override.
        """
        self._session_factory = session_factory or db_manager.session

    # ── Task CRUD ────────────────────────────────────────────────

    async def save_task(
        self, task: SwarmTask, session: Optional[AsyncSession] = None
    ) -> None:
        """Persist a swarm task record with optimistic locking."""
        if session is not None:
            await self._save_task_internal(task, session)
        else:
            async with self._session_factory() as sess:
                async with sess.begin():
                    await self._save_task_internal(task, sess)

    async def _save_task_internal(self, task: SwarmTask, session: AsyncSession) -> None:
        """Persist a swarm task as an idempotent upsert (INSERT or UPDATE).

        The implementation is race-safe: when two sessions call save_task for
        the same task_id concurrently, both may observe a missing row in the
        initial SELECT, and one of them will lose the subsequent INSERT to
        the primary-key UNIQUE constraint. That IntegrityError is recovered
        by rolling back the failed insert (via a SAVEPOINT so the outer
        transaction stays alive), re-fetching the row that the winning
        session committed, and applying the update path.

        See docs/releases/RELEASE_0.9.3_PLATFORM_RUNTIME_STABILIZATION_v2.md
        for the runtime context (LLM-failure replan path triggering the race
        in mission waves).
        """
        expected_version = task.metadata.get("_version", 1)

        def _apply_update(existing: SwarmTaskModel) -> None:
            """Update an existing row in-place, enforcing optimistic locking."""
            if existing.version != expected_version:
                raise JarvisAgentError(
                    code="AGENT_005",
                    message=(
                        f"Optimistic locking conflict on task {task.task_id}: "
                        f"expected version {expected_version}, "
                        f"database has {existing.version}."
                    ),
                )
            existing.goal = task.goal
            existing.priority = task.priority
            existing.status = task.status
            existing.capabilities = task.capabilities
            existing.timeout = task.timeout
            existing.retry = task.retry
            existing.dependencies = (
                [str(d) for d in task.dependencies] if task.dependencies else []
            )
            task.metadata["_version"] = existing.version + 1
            existing.metadata_ = task.metadata
            existing.version += 1

        q = select(SwarmTaskModel).where(SwarmTaskModel.task_id == task.task_id)
        res = await session.execute(q)
        model = res.scalar_one_or_none()

        if model is None:
            # Use a SAVEPOINT for the INSERT attempt so a UNIQUE/PK violation
            # is recovered by rolling back to the savepoint — the outer
            # transaction (opened by the caller via ``async with
            # session.begin():``) stays alive, and the recovery SELECT/UPDATE
            # can proceed without a "Can't operate on closed transaction"
            # error. Pre-CR-005, the code called ``session.rollback()``
            # which closed the outer transaction and crashed the recovery
            # path with a non-deterministic rate (CR-005 flake).
            try:
                async with session.begin_nested():
                    model = SwarmTaskModel(
                        task_id=task.task_id,
                        goal=task.goal,
                        priority=task.priority,
                        status=task.status,
                        capabilities=task.capabilities,
                        timeout=task.timeout,
                        retry=task.retry,
                        dependencies=(
                            [str(d) for d in task.dependencies]
                            if task.dependencies
                            else []
                        ),
                        metadata_=task.metadata,
                        version=1,
                    )
                    session.add(model)
                    # Flush so a UNIQUE/PK violation surfaces here, recoverable
                    # via the except branch below. Without this flush, the
                    # IntegrityError would only be raised at transaction commit
                    # time — outside our try/except — and would crash the
                    # whole session instead of being demoted to an UPDATE.
                    await session.flush()
            except IntegrityError:
                # Concurrent writer won the race: another session INSERTed
                # the same task_id between our SELECT and our flush. The
                # SAVEPOINT has already been rolled back by ``begin_nested``'s
                # context manager; the outer transaction is still alive, so
                # we can re-fetch the row that the winning session committed
                # and apply the update path.
                res = await session.execute(q)
                model = res.scalar_one()
                _apply_update(model)
        else:
            _apply_update(model)

    async def list_tasks(
        self,
        limit: int = 20,
        offset: int = 0,
        session: Optional[AsyncSession] = None,
    ) -> List[SwarmTask]:
        """Fetch paginated task records from the database."""
        if session is not None:
            return await self._list_tasks_internal(limit, offset, session)
        async with self._session_factory() as sess:
            return await self._list_tasks_internal(limit, offset, sess)

    async def _list_tasks_internal(
        self, limit: int, offset: int, session: AsyncSession
    ) -> List[SwarmTask]:
        q = (
            select(SwarmTaskModel)
            .order_by(SwarmTaskModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await session.execute(q)
        models = res.scalars().all()
        return [
            SwarmTask(
                task_id=m.task_id,
                goal=m.goal,
                priority=m.priority,
                capabilities=m.capabilities or [],
                timeout=m.timeout,
                retry=m.retry,
                dependencies=(
                    [UUID(d) for d in m.dependencies] if m.dependencies else []
                ),
                metadata=m.metadata_ or {},
                status=m.status,
            )
            for m in models
        ]

    # ── Agent CRUD ───────────────────────────────────────────────

    async def save_agent(
        self,
        agent_id: UUID,
        agent_data: Dict[str, Any],
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Persist a subagent registration record with optimistic locking."""
        if session is not None:
            await self._save_agent_internal(agent_id, agent_data, session)
        else:
            async with self._session_factory() as sess:
                async with sess.begin():
                    await self._save_agent_internal(agent_id, agent_data, sess)

    async def _save_agent_internal(
        self,
        agent_id: UUID,
        agent_data: Dict[str, Any],
        session: AsyncSession,
    ) -> None:
        q = select(SwarmAgentModel).where(SwarmAgentModel.agent_id == agent_id)
        res = await session.execute(q)
        model = res.scalar_one_or_none()

        expected_version = agent_data.get("_version", 1)

        capabilities = agent_data.get("capabilities", [])
        manifest = agent_data.get("manifest")
        permissions = list(manifest.allowed_permissions) if manifest else []

        if not model:
            model = SwarmAgentModel(
                agent_id=agent_id,
                name=agent_data.get("name", f"Subagent-{agent_id}"),
                status=agent_data.get("status", "ONLINE"),
                capabilities=capabilities,
                permissions=permissions,
                cpu_load=float(agent_data.get("cpu_load", 0.0)),
                memory=float(agent_data.get("memory", 0.0)),
                recent_failures=int(agent_data.get("recent_failures", 0)),
                version=1,
            )
            session.add(model)
        else:
            if model.version != expected_version:
                raise JarvisAgentError(
                    code="AGENT_005",
                    message=(
                        f"Optimistic locking conflict on agent {agent_id}: "
                        f"expected version {expected_version}, "
                        f"database has {model.version}."
                    ),
                )
            model.name = agent_data.get("name", model.name)
            model.status = agent_data.get("status", model.status)
            model.capabilities = capabilities
            model.permissions = permissions
            model.cpu_load = float(agent_data.get("cpu_load", 0.0))
            model.memory = float(agent_data.get("memory", 0.0))
            model.recent_failures = int(agent_data.get("recent_failures", 0))
            agent_data["_version"] = model.version + 1
            model.version += 1

    async def list_agents(
        self,
        limit: int = 20,
        offset: int = 0,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch paginated agent registration records from the database."""
        if session is not None:
            return await self._list_agents_internal(limit, offset, session)
        async with self._session_factory() as sess:
            return await self._list_agents_internal(limit, offset, sess)

    async def _list_agents_internal(
        self, limit: int, offset: int, session: AsyncSession
    ) -> List[Dict[str, Any]]:
        q = (
            select(SwarmAgentModel)
            .order_by(SwarmAgentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await session.execute(q)
        models = res.scalars().all()
        return [
            {
                "agent_id": str(m.agent_id),
                "name": m.name,
                "status": m.status,
                "capabilities": m.capabilities or [],
                "permissions": m.permissions or [],
                "cpu_load": m.cpu_load,
                "memory": m.memory,
                "recent_failures": m.recent_failures,
                "version": m.version,
            }
            for m in models
        ]

    # ── Snapshot CRUD ────────────────────────────────────────────

    async def save_snapshot(
        self,
        snapshot: SwarmSnapshot,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Persist a global swarm snapshot record."""
        if session is not None:
            await self._save_snapshot_internal(snapshot, session)
        else:
            async with self._session_factory() as sess:
                async with sess.begin():
                    await self._save_snapshot_internal(snapshot, sess)

    async def _save_snapshot_internal(
        self, snapshot: SwarmSnapshot, session: AsyncSession
    ) -> None:
        model = SwarmSnapshotModel(
            running_agents=snapshot.running_agents,
            queued_tasks=snapshot.queued_tasks,
            completed_tasks=snapshot.completed_tasks,
            failed_tasks=snapshot.failed_tasks,
            message_rate=snapshot.message_rate,
            cpu_usage=snapshot.cpu_usage,
            memory_usage=snapshot.memory_usage,
            cluster_status=snapshot.cluster_status,
            timestamp=snapshot.timestamp,
        )
        session.add(model)

    async def load_snapshot(
        self, session: Optional[AsyncSession] = None
    ) -> Optional[SwarmSnapshot]:
        """Load the last saved swarm snapshot."""
        if session is not None:
            return await self._load_snapshot_internal(session)
        else:
            async with self._session_factory() as sess:
                return await self._load_snapshot_internal(sess)

    async def _load_snapshot_internal(
        self, session: AsyncSession
    ) -> Optional[SwarmSnapshot]:
        q = (
            select(SwarmSnapshotModel)
            .order_by(SwarmSnapshotModel.timestamp.desc())
            .limit(1)
        )
        res = await session.execute(q)
        model = res.scalar_one_or_none()
        if model:
            return SwarmSnapshot(
                running_agents=model.running_agents,
                queued_tasks=model.queued_tasks,
                completed_tasks=model.completed_tasks,
                failed_tasks=model.failed_tasks,
                message_rate=model.message_rate,
                cpu_usage=model.cpu_usage,
                memory_usage=model.memory_usage,
                cluster_status=model.cluster_status,
                timestamp=model.timestamp,
            )
        return None

    # ── History / Journal CRUD ───────────────────────────────────

    async def save_history(
        self,
        session_id: UUID,
        history: List[Dict[str, Any]],
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Persist subagent message histories or journal iteration records."""
        if session is not None:
            await self._save_history_internal(session_id, history, session)
        else:
            async with self._session_factory() as sess:
                async with sess.begin():
                    await self._save_history_internal(session_id, history, sess)

    async def _save_history_internal(
        self,
        session_id: UUID,
        history: List[Dict[str, Any]],
        session: AsyncSession,
    ) -> None:
        for item in history:
            if "sender" in item and "receiver" in item and "action" in item:
                msg_id = UUID(item["id"]) if item.get("id") else session_id
                corr_id = (
                    UUID(item["correlation_id"])
                    if item.get("correlation_id")
                    else session_id
                )
                model = SwarmMessageModel(
                    id=msg_id,
                    correlation_id=corr_id,
                    sender=item.get("sender"),
                    receiver=item.get("receiver"),
                    action=item.get("action"),
                    body=item.get("body", {}),
                    timestamp=item.get("timestamp", datetime.now(timezone.utc)),
                )
                session.add(model)
            elif "iteration" in item and "chosen_executor" in item:
                model = AgentLoopJournalModel(
                    session_id=session_id,
                    iteration=int(item.get("iteration", 0)),
                    goal_description=item.get("goal_description", ""),
                    chosen_executor=item.get("chosen_executor", ""),
                    reasoning=item.get("reasoning", ""),
                    output_summary=item.get("output_summary", ""),
                    reflection_category=item.get("reflection_category"),
                    next_action=item.get("next_action", "CONTINUE"),
                    timestamp=item.get("timestamp", datetime.now(timezone.utc)),
                )
                session.add(model)

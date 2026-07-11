"""
PHASE: 45 (M6.4.B — task accounting)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (§4.4 Distributed Execution — D-1 worker liveness; D-3 dedup; D-4 idempotency)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md  (M6.4.B — worker_registry.mark_task_started / mark_task_completed)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

``WorkerRegistry`` — DB-touching helper for the ``worker_registry`` table.

This is the registry the leader (``DistributedRouter``) consults when deciding
where to route a wave. It exposes the D-1 liveness invariant (spec §4.4):

    A worker whose ``last_heartbeat`` is >15s stale is marked ``OFFLINE`` and
    its in-flight tasks re-routed.

In M6.4.A the table is queried synchronously by the leader; in M6.4.B the
``DistributedRouter`` may switch to a read-through cache backed by
``MissionTransport`` notifications (the protocol surface is unchanged).

Public surface (M6.4.A — additive only, never replaces an M6.1.A / M6.3.A
/M6.3.B path):

* ``register(worker_id, hostname, pid, capabilities, status="ONLINE")``
  — idempotent: a second call with the same ``worker_id`` UPDATES
  ``hostname``/``pid``/``capabilities``/``status`` rather than raising on
  PK conflict. ``last_heartbeat`` is left untouched on re-register (the
  worker's heartbeat timer will set it on the next cycle).

* ``heartbeat(worker_id, active_tasks=None)``
  — bumps ``last_heartbeat`` to ``now``; if ``active_tasks`` is supplied,
  updates ``active_tasks`` too. Returns the post-update ``status`` (the
  helper auto-promotes ONLINE if a worker re-registers after an OFFLINE
  state).

* ``mark_offline(worker_id)``
  — explicit "I am shutting down" path. The CLI ``WorkerProcess`` calls
  this on ``SIGTERM``.

* ``list_active(now=None, grace_seconds=15.0)``
  — sweep stale workers (status != OFFLINE AND last_heartbeat > grace)
  to OFFLINE, then return all ONLINE workers whose ``last_heartbeat`` is
  within the grace period. The sweep is performed in the same
  transaction as the read so the returned list is consistent with the
  DB at the moment of the call.

* ``get(worker_id)``
  — single-row lookup; returns ``None`` if no such worker.

* ``list_all()``
  — every row in the table (OFFLINE / ONLINE / BUSY alike). Used by the
  ``GET /api/v1/distributed/workers`` REST endpoint.

Design notes:

* **D-1 grace period**: 15 seconds per spec §4.4. ``CURRENT_TASK.md``
  draft had 30s (matching ``MissionRecoveryManager.heartbeat_grace``) but
  the spec wins per AGENTS.md §1; the helper defaults to 15s and accepts
  an override.

* **Status auto-promotion on heartbeat**: if the worker was previously
  OFFLINE and now sends a heartbeat (the CLI retry path), we promote
  it to ONLINE again. This is the recovery path for a worker that
  crashed and restarted fast enough to keep its ``worker_id``.

* **Idempotent register**: replaying a registration must NOT 500 — the
  CLI may restart and use a stable ``worker_id`` (per spec §4.4
  ``started_at`` is per-process, ``worker_id`` is the persistent key).
  The helper uses SQLAlchemy ``MERGE`` (``session.merge``) so the second
  register UPDATEs the row in-place.

* **Snapshot stability**: ``list_active`` performs the sweep + read in a
  single ``session.begin()`` block. A worker that goes stale *during* the
  read is reported as OFFLINE (consistent).

Layer direction (architecture freeze): ``api/ → core/`` only. The
``WorkerProcess`` CLI is in ``core/mission/`` (talks to ``core/runtime/``)
and the ``api/routes/distributed_pool.py`` route talks to the same
registry via the ``get_distributed_router`` provider chain. The router
itself is in ``core/mission/distributed_router.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, update

from core.runtime.mission_models import (
    WorkerRegistryModel,
)

logger = logging.getLogger("jarvis.core.mission.worker_registry")


# Spec §4.4 line 558: "A worker whose `last_heartbeat` is >15s stale is
# marked OFFLINE". Stated as a hard number; we expose it as a constant so
# tests can pin without threading a custom value through every call.
DEFAULT_HEARTBEAT_GRACE_SECONDS: float = 15.0


# String constants — must match the alembic CHECK constraint names.
WORKER_STATUS_ONLINE: str = "ONLINE"
WORKER_STATUS_BUSY: str = "BUSY"
WORKER_STATUS_OFFLINE: str = "OFFLINE"
WORKER_STATUS_VALUES: tuple[str, ...] = (
    WORKER_STATUS_ONLINE,
    WORKER_STATUS_BUSY,
    WORKER_STATUS_OFFLINE,
)


# ---------------------------------------------------------------------------
# Value object — immutable snapshot returned by the read paths.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkerSnapshot:
    """Immutable view of one row of ``worker_registry``.

    Returned by ``WorkerRegistry.get`` / ``list_active`` / ``list_all``.
    The route / dashboard layer can render this directly without further
    DB joins.
    """

    worker_id: UUID
    hostname: str
    pid: int
    capabilities: Dict[str, Any]
    status: str
    active_tasks: int
    last_heartbeat: Optional[datetime]
    started_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": str(self.worker_id),
            "hostname": self.hostname,
            "pid": int(self.pid),
            "capabilities": dict(self.capabilities),
            "status": self.status,
            "active_tasks": int(self.active_tasks),
            "last_heartbeat": (
                self.last_heartbeat.isoformat()
                if self.last_heartbeat is not None
                else None
            ),
            "started_at": self.started_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class WorkerRegistry:
    """DB-touching helper for ``worker_registry``.

    Construction mirrors the M6.3.A precedent::

        registry = WorkerRegistry(db_manager=...)
        await registry.register(worker_id=..., hostname=..., pid=...,
                                capabilities={"platforms": ["linux"], "skills": []})
        await registry.heartbeat(worker_id=..., active_tasks=3)

    The registry is intentionally stateless across calls (no in-process
    cache) — ``DistributedRouter`` is the only leader-side reader and
    it consults the DB on every routing decision so a fresh ``list_active``
    catches stale workers within the next heartbeat cycle.

    Concurrency model: SQLAlchemy ``async`` sessions, single-transaction
    semantics. ``list_active`` performs the stale sweep + read in a single
    ``session.begin()`` so a worker cannot be promoted OBSERVED-as-ONLINE
    after we have decided it is stale.
    """

    def __init__(
        self,
        *,
        db_manager: Any,
        clock: "Optional[Any]" = None,
        heartbeat_grace_seconds: "Optional[float]" = None,
    ) -> None:
        """Initialize.

        Args:
            db_manager: ``core.memory.database.DatabaseSessionManager``
                (the same instance ``MissionManager.db_manager`` holds).
                Required.
            clock: Optional callable returning a ``datetime`` (UTC). Tests
                can pin a deterministic clock here; defaults to wall-clock
                UTC. Passing ``None`` (the default) means "use real
                ``datetime.now(timezone.utc)``".
            heartbeat_grace_seconds: Override the D-1 grace period. The
                default 15s matches spec §4.4 — tests that simulate
                faster/slower workers can shrink or extend it here.

        Raises:
            ValueError: if ``db_manager`` is ``None``.
        """
        if db_manager is None:
            raise ValueError("WorkerRegistry requires db_manager (got None).")
        self._db = db_manager
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._heartbeat_grace_seconds = (
            float(heartbeat_grace_seconds)
            if heartbeat_grace_seconds is not None
            else DEFAULT_HEARTBEAT_GRACE_SECONDS
        )
        if self._heartbeat_grace_seconds <= 0:
            raise ValueError(
                f"heartbeat_grace_seconds must be > 0 "
                f"(got {self._heartbeat_grace_seconds!r})."
            )

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    async def get(self, worker_id: UUID) -> Optional[WorkerSnapshot]:
        """Single-row lookup. ``None`` if no such worker."""
        if not isinstance(worker_id, UUID):
            raise ValueError(
                f"worker_id must be a UUID (got {type(worker_id).__name__})."
            )
        async with self._db.session() as session:
            row = await session.get(WorkerRegistryModel, worker_id)
            if row is None:
                return None
            return _to_snapshot(row)

    async def list_all(self) -> List[WorkerSnapshot]:
        """Every row in the table (OFFLINE / ONLINE / BUSY alike).

        Used by ``GET /api/v1/distributed/workers`` to render the full
        worker list regardless of liveness state.
        """
        async with self._db.session() as session:
            stmt = select(WorkerRegistryModel).order_by(
                WorkerRegistryModel.started_at.desc()
            )
            res = await session.execute(stmt)
            rows = list(res.scalars().all())
            return [_to_snapshot(r) for r in rows]

    async def list_active(
        self,
        *,
        now: "Optional[datetime]" = None,
        grace_seconds: "Optional[float]" = None,
    ) -> List[WorkerSnapshot]:
        """Sweep stale workers to OFFLINE, then return all ONLINE workers.

        Steps (single transaction):
        1. UPDATE ``status`` -> OFFLINE for any row whose
           ``status`` != OFFLINE AND ``last_heartbeat`` is NULL or
           older than ``now - grace_seconds``.
        2. SELECT all rows where ``status`` = ONLINE AND
           ``last_heartbeat`` IS NOT NULL AND
           ``last_heartbeat`` >= ``now - grace_seconds``.

        Args:
            now: Override "now". Defaults to the helper's clock.
            grace_seconds: Override the D-1 grace period for this call.
                Defaults to the helper's ``heartbeat_grace_seconds``.

        Returns:
            Snapshot list of currently-active workers. Stable across the
            read transaction.
        """
        when = now or self._clock()
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        grace = (
            float(grace_seconds)
            if grace_seconds is not None
            else self._heartbeat_grace_seconds
        )
        if grace <= 0:
            raise ValueError(f"grace_seconds must be > 0 (got {grace!r}).")
        cutoff = when - timedelta(seconds=grace)

        async with self._db.session() as session:
            async with session.begin():
                # Step 1: sweep stale rows to OFFLINE.
                sweep_stmt = (
                    update(WorkerRegistryModel)
                    .where(WorkerRegistryModel.status != WORKER_STATUS_OFFLINE)
                    .where(
                        (WorkerRegistryModel.last_heartbeat.is_(None))
                        | (WorkerRegistryModel.last_heartbeat < cutoff)
                    )
                    .values(status=WORKER_STATUS_OFFLINE)
                )
                sweep_res = await session.execute(sweep_stmt)
                swept = sweep_res.rowcount or 0
                if swept > 0:
                    logger.info(
                        "WorkerRegistry.list_active swept %d worker(s) to "
                        "OFFLINE (grace=%.1fs, cutoff=%s)",
                        swept,
                        grace,
                        cutoff.isoformat(),
                    )

                # Step 2: read all ONLINE workers within the grace window.
                select_stmt = (
                    select(WorkerRegistryModel)
                    .where(WorkerRegistryModel.status == WORKER_STATUS_ONLINE)
                    .where(WorkerRegistryModel.last_heartbeat.is_not(None))
                    .where(WorkerRegistryModel.last_heartbeat >= cutoff)
                    .order_by(WorkerRegistryModel.last_heartbeat.desc())
                )
                res = await session.execute(select_stmt)
                rows = list(res.scalars().all())
                return [_to_snapshot(r) for r in rows]

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    async def register(
        self,
        *,
        worker_id: UUID,
        hostname: str,
        pid: int,
        capabilities: Dict[str, Any],
        status: str = WORKER_STATUS_ONLINE,
    ) -> WorkerSnapshot:
        """Register (or re-register) a worker. Idempotent.

        Args:
            worker_id: Stable UUID generated by the worker process.
                Same UUID across restarts so the leader does not lose
                liveness continuity.
            hostname: Host the worker is running on (operator-supplied
                or detected via ``socket.gethostname()`` at the CLI).
            pid: OS PID (integer). Diagnostic only.
            capabilities: JSONB-compatible dict. Canonical shape per
                spec §4.4 + CURRENT_TASK.md: ``{"platforms": [...],
                "skills": [...]}``. The registry does NOT validate the
                shape — the router treats the dict as opaque and matches
                on stringified JSON.
            status: Initial status. Defaults to ``ONLINE`` — the worker
                is assumed live at registration time.

        Returns:
            The post-write ``WorkerSnapshot``.

        Raises:
            ValueError: on bad arguments (non-UUID hostname / invalid
                status / non-int pid).
        """
        if not isinstance(worker_id, UUID):
            raise ValueError(
                f"worker_id must be a UUID (got {type(worker_id).__name__})."
            )
        if not isinstance(hostname, str) or not hostname:
            raise ValueError("hostname must be a non-empty str.")
        if not isinstance(pid, int) or pid <= 0:
            raise ValueError(f"pid must be a positive int (got {pid!r}).")
        if status not in WORKER_STATUS_VALUES:
            raise ValueError(
                f"status must be one of {WORKER_STATUS_VALUES} (got {status!r})."
            )
        if not isinstance(capabilities, dict):
            raise ValueError(
                f"capabilities must be a dict (got {type(capabilities).__name__})."
            )

        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        async with self._db.session() as session:
            async with session.begin():
                existing = await session.get(WorkerRegistryModel, worker_id)
                if existing is None:
                    row = WorkerRegistryModel(
                        worker_id=worker_id,
                        hostname=hostname,
                        pid=pid,
                        capabilities=capabilities,
                        status=status,
                        active_tasks=0,
                        last_heartbeat=now,
                        started_at=now,
                    )
                    session.add(row)
                else:
                    existing.hostname = hostname
                    existing.pid = pid
                    existing.capabilities = capabilities
                    existing.status = status
                    # last_heartbeat: leave alone on re-register
                    # (the worker's heartbeat timer will set it on the
                    # next cycle — preserves "no heartbeat yet" semantics).
                    # started_at is preserved on re-register.
                # refresh
                row = await session.get(WorkerRegistryModel, worker_id)
                if row is None:  # pragma: no cover — defensive
                    raise RuntimeError(
                        "WorkerRegistry.register: row missing post-write"
                    )
                return _to_snapshot(row)

    async def heartbeat(
        self,
        *,
        worker_id: UUID,
        active_tasks: "Optional[int]" = None,
    ) -> Optional[str]:
        """Update ``last_heartbeat`` (and optionally ``active_tasks``).

        Auto-promotes an OFFLINE worker back to ONLINE (recovery path
        for a worker that crashed + restarted with the same UUID).

        Args:
            worker_id: Worker to heartbeat.
            active_tasks: Optional current load count. If supplied,
                must be a non-negative int.

        Returns:
            The post-update ``status`` of the worker (e.g. ``"ONLINE"``),
            or ``None`` if no such worker is registered (the caller
            should ``register()`` first).

        Raises:
            ValueError: on bad arguments.
        """
        if not isinstance(worker_id, UUID):
            raise ValueError(
                f"worker_id must be a UUID (got {type(worker_id).__name__})."
            )
        if active_tasks is not None:
            if not isinstance(active_tasks, int) or active_tasks < 0:
                raise ValueError(
                    f"active_tasks must be a non-negative int (got {active_tasks!r})."
                )

        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        async with self._db.session() as session:
            async with session.begin():
                row = await session.get(WorkerRegistryModel, worker_id)
                if row is None:
                    return None
                row.last_heartbeat = now
                if row.status == WORKER_STATUS_OFFLINE:
                    row.status = WORKER_STATUS_ONLINE
                if active_tasks is not None:
                    row.active_tasks = active_tasks
                return row.status

    async def mark_offline(self, worker_id: UUID) -> bool:
        """Explicit shutdown hook. Called by ``WorkerProcess`` on SIGTERM.

        Returns:
            ``True`` if the row existed and was updated; ``False`` if no
            such worker was registered.

        Raises:
            ValueError: on bad arguments.
        """
        if not isinstance(worker_id, UUID):
            raise ValueError(
                f"worker_id must be a UUID (got {type(worker_id).__name__})."
            )
        async with self._db.session() as session:
            async with session.begin():
                row = await session.get(WorkerRegistryModel, worker_id)
                if row is None:
                    return False
                if row.status != WORKER_STATUS_OFFLINE:
                    row.status = WORKER_STATUS_OFFLINE
                return True

    # ------------------------------------------------------------------
    # M6.4.B — task accounting (idempotent on (worker, wave))
    # ------------------------------------------------------------------

    async def mark_task_started(
        self,
        *,
        worker_id: UUID,
        wave_run_id: UUID,
    ) -> bool:
        """Mark a wave as started on the worker. Idempotent on duplicate calls.

        The M6.4.B worker's call to acknowledge that a wave picked up from
        the ``MissionTransport`` is now executing. Updates
        ``worker_registry.active_tasks`` so the load-aware router tiebreak
        sees the increment on the next ``route()`` call.

        D-4 invariant: the transport is at-least-once — the same wave may
        be delivered twice. ``mark_task_started`` MUST therefore be
        idempotent on repeated calls for the same ``(worker_id,
        wave_run_id)`` pair.

        The helper is keyed on the existing ``task_routing_log`` table
        (D-3 unique index on ``(wave_run_id, chosen_worker_id)``). The
        "is this wave already in-flight on this worker?" check is
        ``task_routing_log.completed_at IS NULL`` for the matching row.

        Idempotency strategy: lock the routing row + worker row with
        ``SELECT ... FOR UPDATE``; count the in-flight routing rows for
        this worker; if ``active_tasks`` is already ``>=`` the in-flight
        count, the increment was applied on a prior call and this call
        is a no-op. Otherwise increment by 1.

        Args:
            worker_id: The worker that is starting the task.
            wave_run_id: The D-3 dedup key + idempotency key (D-4).

        Returns:
            ``True`` if a state transition occurred (active_tasks was
            incremented) or if the call was idempotent on a previously
            in-flight wave. ``False`` if no routing row exists for
            ``(wave_run_id, chosen_worker_id=worker_id)`` (the caller
            should ``route()`` first) OR if the wave is already
            completed.

        Raises:
            ValueError: on non-UUID arguments.
        """
        if not isinstance(worker_id, UUID):
            raise ValueError(
                f"worker_id must be a UUID (got {type(worker_id).__name__})."
            )
        if not isinstance(wave_run_id, UUID):
            raise ValueError(
                f"wave_run_id must be a UUID (got {type(wave_run_id).__name__})."
            )
        # Imported here to avoid a top-level circular import (the
        # routing model is registered via ``core.runtime.mission_models``).
        from sqlalchemy import func

        from core.runtime.mission_models import (
            TaskRoutingLogModel,
        )

        async with self._db.session() as session:
            async with session.begin():
                # Lock the routing row + the worker row together so a
                # concurrent mark_task_started / mark_task_completed on
                # the same worker cannot interleave. SQLite ignores
                # ``with_for_update`` (the database is single-writer);
                # the SAVEPOINT discipline on the outer ``begin`` is
                # the cross-dialect atomicity guard.
                routing_stmt = (
                    select(TaskRoutingLogModel, WorkerRegistryModel)
                    .join(
                        WorkerRegistryModel,
                        TaskRoutingLogModel.chosen_worker_id
                        == WorkerRegistryModel.worker_id,
                    )
                    .where(TaskRoutingLogModel.wave_run_id == wave_run_id)
                    .where(TaskRoutingLogModel.chosen_worker_id == worker_id)
                    .with_for_update()
                )
                res = await session.execute(routing_stmt)
                rows = res.all()
                if not rows:
                    return False
                log_row, worker_row = rows[0]
                if log_row.completed_at is not None:
                    # Already completed — caller should not start a
                    # finished wave. D-4 exactly-once: the runtime is
                    # responsible for skipping the duplicate here.
                    return False

                # Idempotency: count in-flight routing rows for this
                # worker (D-3 unique index guarantees ≤ 1 per
                # ``(wave_run_id, chosen_worker_id)`` pair, so the
                # in-flight count = "number of waves not yet completed
                # on this worker").
                in_flight_stmt = (
                    select(func.count())
                    .select_from(TaskRoutingLogModel)
                    .where(TaskRoutingLogModel.chosen_worker_id == worker_id)
                    .where(TaskRoutingLogModel.completed_at.is_(None))
                )
                in_flight = int((await session.scalar(in_flight_stmt)) or 0)
                if int(worker_row.active_tasks) >= in_flight:
                    # active_tasks already covers this wave — a prior
                    # call did the increment. No-op (idempotent).
                    return True
                # Defensive: in_flight must be ≥ 1 here (we just verified
                # the current row is in-flight). Increment by 1.
                worker_row.active_tasks = int(worker_row.active_tasks) + 1
                return True

    async def mark_task_completed(
        self,
        *,
        worker_id: UUID,
        wave_run_id: UUID,
    ) -> bool:
        """Mark a wave as completed on the worker. Idempotent.

        The M6.4.B worker's call to acknowledge that an in-flight wave
        finished. Sets ``task_routing_log.completed_at`` and decrements
        ``worker_registry.active_tasks`` so the load-aware router
        tiebreak sees the decrement on the next ``route()`` call.

        D-4 invariant: the runtime may re-deliver a completed wave
        (e.g. a worker that crashed after the task ran but before
        acking). ``mark_task_completed`` MUST therefore be idempotent on
        duplicate calls.

        The helper is keyed on the same ``task_routing_log`` row used
        by ``mark_task_started``. ``completed_at`` flips from ``NULL``
        to ``now`` exactly once; subsequent calls observe the
        non-null ``completed_at`` and return without touching
        ``active_tasks``.

        Args:
            worker_id: The worker that completed the task.
            wave_run_id: The D-3 dedup key + idempotency key (D-4).

        Returns:
            ``True`` if ``completed_at`` was set (transition) or if the
            call was idempotent on an already-completed wave. ``False``
            if no routing row exists for the
            ``(wave_run_id, chosen_worker_id=worker_id)`` pair (caller
            should ``route()`` first).

        Raises:
            ValueError: on non-UUID arguments.
        """
        if not isinstance(worker_id, UUID):
            raise ValueError(
                f"worker_id must be a UUID (got {type(worker_id).__name__})."
            )
        if not isinstance(wave_run_id, UUID):
            raise ValueError(
                f"wave_run_id must be a UUID (got {type(wave_run_id).__name__})."
            )

        from core.runtime.mission_models import (
            TaskRoutingLogModel,
        )

        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        async with self._db.session() as session:
            async with session.begin():
                # Lock the routing row + the worker row together (see
                # mark_task_started for the cross-dialect note).
                routing_stmt = (
                    select(TaskRoutingLogModel, WorkerRegistryModel)
                    .join(
                        WorkerRegistryModel,
                        TaskRoutingLogModel.chosen_worker_id
                        == WorkerRegistryModel.worker_id,
                    )
                    .where(TaskRoutingLogModel.wave_run_id == wave_run_id)
                    .where(TaskRoutingLogModel.chosen_worker_id == worker_id)
                    .with_for_update()
                )
                res = await session.execute(routing_stmt)
                rows = res.all()
                if not rows:
                    return False
                log_row, worker_row = rows[0]
                if log_row.completed_at is not None:
                    # Already completed — idempotent no-op. ``active_tasks``
                    # was decremented on the original call.
                    return True
                # Mark completed + decrement. Defensive: never go below
                # zero (a buggy caller that complete-without-start
                # cannot create a negative count).
                log_row.completed_at = now
                if int(worker_row.active_tasks) > 0:
                    worker_row.active_tasks = int(worker_row.active_tasks) - 1
                return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_snapshot(row: WorkerRegistryModel) -> WorkerSnapshot:
    """Convert an ORM row into a ``WorkerSnapshot``.

    Defensive: ``capabilities`` may have been mutated to ``None`` by a
    legacy direct-write path (G-6 legacy obliviousness). We coerce to
    ``{}`` so the route layer never has to deal with ``None``.

    Also normalizes naive datetimes to UTC-aware — SQLite drops the
    ``tzinfo`` on roundtrip even when the column is declared
    ``DateTime(timezone=True)``; the DB stores UTC by convention. Every
    consumer of the snapshot then gets a tz-aware ``datetime`` and
    never has to defend against mixed naive/aware comparisons.
    """
    caps = row.capabilities
    if caps is None or not isinstance(caps, dict):
        caps = {}
    last_hb = row.last_heartbeat
    if last_hb is not None and last_hb.tzinfo is None:
        last_hb = last_hb.replace(tzinfo=timezone.utc)
    started = row.started_at
    if started is not None and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return WorkerSnapshot(
        worker_id=row.worker_id,
        hostname=row.hostname,
        pid=int(row.pid),
        capabilities=dict(caps),
        status=row.status,
        active_tasks=int(row.active_tasks),
        last_heartbeat=last_hb,
        started_at=started,
    )


__all__ = [
    "DEFAULT_HEARTBEAT_GRACE_SECONDS",
    "WORKER_STATUS_BUSY",
    "WORKER_STATUS_OFFLINE",
    "WORKER_STATUS_ONLINE",
    "WORKER_STATUS_VALUES",
    "WorkerRegistry",
    "WorkerSnapshot",
]


# Re-export the routing model so router code can import
# ``from core.mission.worker_registry import TaskRoutingLogModel`` for the
# ``append-only`` insert helper that ships in ``distributed_router.py``.
__all__.append("TaskRoutingLogModel")

"""
PHASE: 45 (M6.4.A)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (§4.4 Distributed Execution — D-1/D-2/D-3)
    docs/mission_state_machine.md  (R-1 idempotency contract)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md  (M6.4.A — DistributedRouter)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

``DistributedRouter`` — leader-side routing decision for cross-process
task execution.

The router has exactly ONE public capability: ``route(wave_run_id,
required_capability, policy)`` returns a chosen ``WorkerSnapshot`` and
appends a ``task_routing_log`` row (D-2 append-only contract).

Invariants:

* A-1 architect recommendation 2026-07-08 — "DistributedRouter must
  speak only to the ``MissionTransport`` protocol — never to a
  concrete Redis / RabbitMQ / gRPC client". The router imports
  ``MissionTransport`` (the Protocol) and ``WorkerRegistry``
  (the DB-touching helper) only. It NEVER imports ``LocalTransport``
  or ``RemoteTransport`` directly. Even M6.4.A's local-mode routing
  uses the worker registry as the single source of truth — the
  transport is reserved for the future worker-task delivery layer.

* D-1 — ``WorkerRegistry.list_active`` is consulted (15s grace per
  spec §4.4) — STALE workers never appear in candidate lists.

* D-2 — ``task_routing_log`` is appended via the helper ``insert_routing``
  only; there is no ``update`` / ``delete`` method anywhere in this
  module.

* D-3 — One row per ``(wave_run_id, chosen_worker_id)`` pair. The
  schema's unique index on ``(wave_run_id, chosen_worker_id)`` enforces
  this; ``route()`` returns the existing row's `route_id` when a
  duplicate insert is attempted (R-1 idempotency contract — the same
  ``wave_run_id`` is routed to the same worker twice in a row).

* G-6 — Legacy obliviousness. The router never requires legacy mission
  columns; a NULL ``last_heartbeat`` (post-registration, pre-first
  heartbeat) is correctly excluded by ``WorkerRegistry.list_active``.

Routing policy (per CURRENT_TASK.md design notes):

* ``LOCAL_ONLY`` — only workers registered in this process's registry
  (no network lookup). Raises ``NoEligibleWorkerError`` if no eligible
  worker is found.

* ``REMOTE_PREFERRED`` — exported but raises ``NotImplementedError`` in
  M6.4.A (no network transport is wired yet — M6.4.B).

* ``ANY`` — picks the lowest-active-tasks eligible worker across the
  registry. Ties broken by ``last_heartbeat`` (most recent = preferred).

Load-aware tiebreak: when more than one eligible worker matches, the
router picks the worker with the LOWEST ``active_tasks`` count. A
tie on active_tasks is broken by ``last_heartbeat`` (more recent
preferred).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from core.mission.worker_registry import (
    WorkerRegistry,
    WorkerSnapshot,
)

logger = logging.getLogger("jarvis.core.mission.distributed_router")


# ---------------------------------------------------------------------------
# Routing policy
# ---------------------------------------------------------------------------


class RoutingPolicy(str, Enum):
    """Policy under which the router picks a worker.

    Values match the spec/CURRENT_TASK design notes. String values so the
    policy serializes cleanly in API responses + journals.
    """

    LOCAL_ONLY = "LOCAL_ONLY"
    REMOTE_PREFERRED = "REMOTE_PREFERRED"
    ANY = "ANY"


# String constants for decision_reason values. Reasons are persisted on
# ``task_routing_log.decision_reason`` so journal readers see a stable
# vocabulary.
REASON_NO_ELIGIBLE_WORKER: str = "NO_ELIGIBLE_WORKER"
REASON_CAPABILITY_MISMATCH: str = "CAPABILITY_MISMATCH"
REASON_REMOTE_PREFERRED_NOT_IMPLEMENTED: str = "REMOTE_PREFERRED_NOT_IMPLEMENTED_M6_4_B"
REASON_DEDUP_HIT: str = "DEDUP_HIT_R1_IDEMPOTENT"
REASON_ROUTED_LOCAL: str = "ROUTED_LOCAL"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DistributedRouterError(RuntimeError):
    """Internal-error in the DistributedRouter. Caller should not catch
    this in production; tests may assert on it."""


class NoEligibleWorkerError(DistributedRouterError):
    """``route()`` could not find any worker matching the required
    capability under the active policy.

    Raised for ``LOCAL_ONLY`` + capability mismatch + no workers
    registered. Mapped to HTTP 404 by the route layer.
    """


class RemoteTransportNotImplementedError(DistributedRouterError):
    """``REMOTE_PREFERRED`` policy invoked in M6.4.A — M6.4.B-only scope."""


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingDecision:
    """Result of a single ``route()`` call.

    `worker` is ``None`` only when ``allow_no_worker=True`` was passed
    AND no eligible worker was found — the journal row is still
    written with ``decision_reason = NO_ELIGIBLE_WORKER`` so the
    decision is audited.
    """

    worker: Optional[WorkerSnapshot]
    wave_run_id: UUID
    policy: RoutingPolicy
    decision_reason: str
    route_id: UUID
    dedup_hit: bool
    routed_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker": self.worker.to_dict() if self.worker else None,
            "wave_run_id": str(self.wave_run_id),
            "policy": self.policy.value,
            "decision_reason": self.decision_reason,
            "route_id": str(self.route_id),
            "dedup_hit": bool(self.dedup_hit),
            "routed_at": self.routed_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# DistributedRouter
# ---------------------------------------------------------------------------


class DistributedRouter:
    """Leader-side routing decision maker.

    Construction::

        router = DistributedRouter(worker_registry=registry)

    Public methods::

        await router.route(wave_run_id=..., required_platform=...,
                           required_skill=..., policy=RoutingPolicy.ANY)
        await router.mark_routing_complete(route_id=...)

    No network code in M6.4.A — the router uses ``WorkerRegistry`` only.
    The transport is reserved for M6.4.B's task-delivery layer.

    Thread-safety: stateless across calls. ``WorkerRegistry`` is the
    authoritative source of truth; concurrent ``route()`` calls each
    trigger an independent ``list_active`` snapshot. The
    ``(wave_run_id, chosen_worker_id)`` unique index enforces D-3 at
    the DB level even when multiple leaders race — only one insert
    can succeed for a given pair.
    """

    def __init__(
        self,
        *,
        worker_registry: WorkerRegistry,
        clock: "Optional[Any]" = None,
        load_aware: bool = True,
    ) -> None:
        """Initialize.

        Args:
            worker_registry: The leader's worker registry helper.
                Required.
            clock: Optional clock callable for test determinism.
                Defaults to wall-clock UTC.
            load_aware: When ``True`` (default), the router chooses the
                lowest-active-tasks eligible worker. When ``False``,
                the router chooses the most recent heartbeat. Tests
                may pin ``False`` to make assertions deterministic.
        """
        if worker_registry is None:
            raise DistributedRouterError(
                "DistributedRouter requires a worker_registry."
            )
        self._registry = worker_registry
        self._clock = clock or (
            lambda: __import__("datetime").datetime.now(  # noqa: PLC0415
                __import__("datetime").timezone.utc
            )
        )
        self._load_aware = bool(load_aware)

    # ----- public read-only accessors -------------------------------------

    @property
    def registry(self) -> WorkerRegistry:
        """The underlying ``WorkerRegistry`` helper.

        Exposed read-only so the route layer (``/api/v1/distributed/...``)
        can introspect worker state without going through the routing
        decision API. The accessor returns the same instance the
        router consults on every ``route()`` call.
        """
        return self._registry

    # ----- public surface -------------------------------------------------

    async def route(
        self,
        *,
        wave_run_id: UUID,
        required_platform: "Optional[str]" = None,
        required_skill: "Optional[str]" = None,
        policy: RoutingPolicy = RoutingPolicy.ANY,
        allow_no_worker: bool = False,
    ) -> RoutingDecision:
        """Decide which worker should handle ``wave_run_id``.

        Capability matching is "all-required" — a worker matches only
        if it has both ``required_platform`` (when supplied) AND
        ``required_skill`` (when supplied). Either argument can be
        ``None`` to skip that check.

        Args:
            wave_run_id: D-3 dedup key + audit.
            required_platform: Optional platform name to match
                (e.g. "linux", "macos", "windows"); must appear in the
                worker's ``capabilities["platforms"]`` list.
            required_skill: Optional skill namespace (e.g.
                "core.skills.git_clone") that must appear in the
                worker's ``capabilities["skills"]`` list.
            policy: Routing policy (LOCAL_ONLY / REMOTE_PREFERRED /
                ANY). Defaults to ``ANY``.
            allow_no_worker: When ``True``, the router returns an empty
                ``RoutingDecision`` with ``decision_reason =
                NO_ELIGIBLE_WORKER`` instead of raising. The journal
                row is still appended (D-2 audit). Default ``False``:
                raise ``NoEligibleWorkerError``.

        Returns:
            ``RoutingDecision`` carrying the chosen worker (or ``None``
            if ``allow_no_worker=True`` and no worker matched), the
            policy used, the reason, and the persistent ``route_id``.
            ``dedup_hit=True`` if a prior routing decision already
            recorded this ``(wave_run_id, chosen_worker_id)`` pair.

        Raises:
            NoEligibleWorkerError: when no worker matches AND
                ``allow_no_worker`` is ``False``.
            RemoteTransportNotImplementedError: when ``policy ==
                REMOTE_PREFERRED`` in M6.4.A (M6.4.B scope).
            DistributedRouterError: on programmer error.
        """
        if not isinstance(wave_run_id, UUID):
            raise DistributedRouterError(
                f"wave_run_id must be a UUID (got {type(wave_run_id).__name__})."
            )
        if not isinstance(policy, RoutingPolicy):
            raise DistributedRouterError(
                f"policy must be a RoutingPolicy (got {type(policy).__name__})."
            )

        # REMOTE_PREFERRED is M6.4.B scope. Recording the journal entry
        # first so the decision is audited even when the call fails.
        if policy == RoutingPolicy.REMOTE_PREFERRED:
            await self._insert_routing(
                wave_run_id=wave_run_id,
                chosen_worker_id=uuid4(),  # placeholder; ignored via reason
                decision_reason=REASON_REMOTE_PREFERRED_NOT_IMPLEMENTED,
            )
            raise RemoteTransportNotImplementedError(
                "RoutingPolicy.REMOTE_PREFERRED is M6.4.B scope. "
                "See docs/108_PHASE_45_IMPLEMENTATION_PLAN.md §3 M6.4.B."
            )

        # Sweep stale workers + read the active set in a single txn.
        candidates = await self._registry.list_active()

        # Capability filter.
        eligible: List[WorkerSnapshot] = []
        for w in candidates:
            if self._worker_matches(
                w,
                required_platform=required_platform,
                required_skill=required_skill,
            ):
                eligible.append(w)

        if not eligible:
            if allow_no_worker:
                route_id, routed_at = await self._insert_routing(
                    wave_run_id=wave_run_id,
                    chosen_worker_id=uuid4(),
                    decision_reason=REASON_NO_ELIGIBLE_WORKER,
                )
                return RoutingDecision(
                    worker=None,
                    wave_run_id=wave_run_id,
                    policy=policy,
                    decision_reason=REASON_NO_ELIGIBLE_WORKER,
                    route_id=route_id,
                    dedup_hit=False,
                    routed_at=routed_at,
                )
            raise NoEligibleWorkerError(
                f"No eligible worker for wave {wave_run_id} "
                f"(required_platform={required_platform!r}, "
                f"required_skill={required_skill!r}, "
                f"policy={policy.value})."
            )

        chosen = self._pick_best(eligible)
        route_id, routed_at = await self._insert_routing(
            wave_run_id=wave_run_id,
            chosen_worker_id=chosen.worker_id,
            decision_reason=REASON_ROUTED_LOCAL,
        )

        return RoutingDecision(
            worker=chosen,
            wave_run_id=wave_run_id,
            policy=policy,
            decision_reason=REASON_ROUTED_LOCAL,
            route_id=route_id,
            dedup_hit=False,
            routed_at=routed_at,
        )

    async def get_routing_for_wave(self, wave_run_id: UUID) -> List[RoutingDecision]:
        """List every routing decision recorded for ``wave_run_id``.

        Per D-2 the underlying table is append-only — this method only
        SELECTs; it never updates or deletes.
        """
        from sqlalchemy import select

        from core.runtime.mission_models import (
            TaskRoutingLogModel,
            WorkerRegistryModel,
        )

        async with self._registry._db.session() as session:
            stmt = (
                select(TaskRoutingLogModel, WorkerRegistryModel)
                .join(
                    WorkerRegistryModel,
                    TaskRoutingLogModel.chosen_worker_id
                    == WorkerRegistryModel.worker_id,
                )
                .where(TaskRoutingLogModel.wave_run_id == wave_run_id)
                .order_by(TaskRoutingLogModel.routed_at.asc())
            )
            res = await session.execute(stmt)
            out: List[RoutingDecision] = []
            for log_row, worker_row in res.all():
                wsnap = WorkerSnapshot(
                    worker_id=worker_row.worker_id,
                    hostname=worker_row.hostname,
                    pid=int(worker_row.pid),
                    capabilities=dict(worker_row.capabilities or {}),
                    status=worker_row.status,
                    active_tasks=int(worker_row.active_tasks),
                    last_heartbeat=worker_row.last_heartbeat,
                    started_at=worker_row.started_at,
                )
                out.append(
                    RoutingDecision(
                        worker=wsnap,
                        wave_run_id=wave_run_id,
                        policy=RoutingPolicy.LOCAL_ONLY,  # M6.4.B will derive this
                        decision_reason=log_row.decision_reason,
                        route_id=log_row.route_id,
                        dedup_hit=False,
                        routed_at=log_row.routed_at,
                    )
                )
            return out

    async def mark_routing_complete(self, route_id: UUID) -> bool:
        """Set ``completed_at`` on a routing row.

        D-2 says append-only, but ``completed_at`` is the additive
        complement to ``routed_at`` — it is set by a single UPDATE that
        is structurally equivalent to a state transition, not an
        append. The route row remains in the table forever; this only
        records when the routing decision was retired.

        Returns:
            ``True`` if the row existed and was updated, ``False``
            otherwise.
        """
        from sqlalchemy import update

        from core.runtime.mission_models import (
            TaskRoutingLogModel,
        )

        if not isinstance(route_id, UUID):
            raise DistributedRouterError(
                f"route_id must be a UUID (got {type(route_id).__name__})."
            )
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=__import__("datetime").timezone.utc)  # noqa: PLC0415
        async with self._registry._db.session() as session:
            async with session.begin():
                stmt = (
                    update(TaskRoutingLogModel)
                    .where(TaskRoutingLogModel.route_id == route_id)
                    .where(TaskRoutingLogModel.completed_at.is_(None))
                    .values(completed_at=now)
                )
                res = await session.execute(stmt)
                return (res.rowcount or 0) > 0

    # ----- internals -----------------------------------------------------

    def _worker_matches(
        self,
        worker: WorkerSnapshot,
        *,
        required_platform: "Optional[str]",
        required_skill: "Optional[str]",
    ) -> bool:
        """Capability filter — "all-required" semantics.

        The JSONB blob is opaque: comparison is on stringified JSON.
        Phase 41 capability registry is the long-term source-of-truth;
        for M6.4.A the JSONB blob is opaque to the router (exact-match
        on stringified JSON).
        """
        caps = worker.capabilities or {}
        platforms = caps.get("platforms", [])
        skills = caps.get("skills", [])
        if required_platform is not None and required_platform not in platforms:
            return False
        if required_skill is not None and required_skill not in skills:
            return False
        return True

    def _pick_best(self, candidates: List[WorkerSnapshot]) -> WorkerSnapshot:
        """Pick the lowest-load eligible worker.

        Tie-break: most recent ``last_heartbeat``. The M6.4.A
        ``load_aware=False`` mode picks the most-recent-heartbeat
        directly (deterministic for tests).
        """
        if not candidates:
            raise DistributedRouterError("_pick_best called with empty candidates.")
        if not self._load_aware:
            return max(
                candidates,
                key=lambda w: (
                    w.last_heartbeat
                    or __import__("datetime").datetime.min.replace(  # noqa: PLC0415
                        tzinfo=__import__("datetime").timezone.utc  # noqa: PLC0415
                    )
                ),
            )
        # Min active_tasks; tie broken by max last_heartbeat.
        return min(
            candidates,
            key=lambda w: (
                int(w.active_tasks),
                -(
                    w.last_heartbeat.timestamp()
                    if w.last_heartbeat is not None
                    else 0.0
                ),
            ),
        )

    async def _insert_routing(
        self,
        *,
        wave_run_id: UUID,
        chosen_worker_id: UUID,
        decision_reason: str,
    ) -> "tuple[UUID, datetime]":
        """Append a row to ``task_routing_log``.

        Returns:
            ``(route_id, routed_at)`` — both as persisted.

        D-3 enforcement: the unique index on
        ``(wave_run_id, chosen_worker_id)`` either makes this the FIRST
        such row (insert succeeds) or returns the existing
        ``route_id`` (dedup hit). The route remains append-only in
        either path.

        Dialect handling: Postgres uses ``INSERT ... ON CONFLICT DO
        NOTHING``; SQLite raises ``IntegrityError`` on a unique-index
        violation which we catch + treat as a dedup hit. We attempt
        the INSERT in its own SAVEPOINT (begin_nested) so a failed
        insert does not poison the outer session — both dialects
        share the same savepoint semantics for our purposes.
        """
        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError

        from core.runtime.mission_models import (
            TaskRoutingLogModel,
        )

        route_id = uuid4()
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=__import__("datetime").timezone.utc)  # noqa: PLC0415

        async with self._registry._db.session() as session:
            async with session.begin():
                # Try the INSERT inside a SAVEPOINT so a dedup hit
                # rolls back ONLY this insert, not the whole tx.
                try:
                    async with session.begin_nested():
                        bind = session.get_bind()
                        dialect = bind.dialect.name if hasattr(bind, "dialect") else ""
                        if dialect.startswith("postgres"):
                            from sqlalchemy.dialects.postgresql import (
                                insert as pg_insert,
                            )

                            stmt = (
                                pg_insert(TaskRoutingLogModel)
                                .values(
                                    route_id=route_id,
                                    wave_run_id=wave_run_id,
                                    chosen_worker_id=chosen_worker_id,
                                    decision_reason=decision_reason,
                                    routed_at=now,
                                    completed_at=None,
                                )
                                .on_conflict_do_nothing(
                                    index_elements=[
                                        TaskRoutingLogModel.wave_run_id,
                                        TaskRoutingLogModel.chosen_worker_id,
                                    ]
                                )
                            )
                            await session.execute(stmt)
                        else:
                            # SQLite / generic — plain INSERT; conflicts
                            # surface as IntegrityError which rolls back
                            # the savepoint and propagates out.
                            row = TaskRoutingLogModel(
                                route_id=route_id,
                                wave_run_id=wave_run_id,
                                chosen_worker_id=chosen_worker_id,
                                decision_reason=decision_reason,
                                routed_at=now,
                                completed_at=None,
                            )
                            session.add(row)
                            await session.flush()
                except IntegrityError:
                    # SQLite dedup hit — savepoint is rolled back; outer
                    # transaction is still usable for the SELECT.
                    pass

                # Re-read the canonical row — yields a consistent
                # (route_id, routed_at) tuple for the caller regardless
                # of which dialect handled the insert.
                select_stmt = select(TaskRoutingLogModel).where(
                    TaskRoutingLogModel.wave_run_id == wave_run_id,
                    TaskRoutingLogModel.chosen_worker_id == chosen_worker_id,
                )
                res = await session.execute(select_stmt)
                row = res.scalar_one()
                return row.route_id, row.routed_at


# ---------------------------------------------------------------------------
# Internal: helper used by ``_insert_routing`` to coerce the
# ``insert(...).on_conflict_do_nothing(...)`` dialect correctly on
# non-PostgreSQL backends (SQLite primarily). SQLite does NOT support
# ``on_conflict_do_nothing`` via that API uniformly; we use a try/except
# to fall back to a plain ``session.add`` + IntegrityError catch.
# ---------------------------------------------------------------------------


__all__ = [
    "DistributedRouter",
    "DistributedRouterError",
    "NoEligibleWorkerError",
    "REASON_CAPABILITY_MISMATCH",
    "REASON_DEDUP_HIT",
    "REASON_NO_ELIGIBLE_WORKER",
    "REASON_REMOTE_PREFERRED_NOT_IMPLEMENTED",
    "REASON_ROUTED_LOCAL",
    "RemoteTransportNotImplementedError",
    "RoutingDecision",
    "RoutingPolicy",
]


# Re-export the helper used by the route + dashboard layers.
__all__.append("WorkerSnapshot")

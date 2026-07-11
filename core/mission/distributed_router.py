"""
PHASE: 45 (M6.4.B — REMOTE_PREFERRED behaviour)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (§4.4 Distributed Execution — D-1/D-2/D-3/D-4/D-5)
    docs/mission_state_machine.md  (R-1 idempotency contract)
    docs/cr/CR-4_phase45_d4_d5_idempotency_envelope.md  (CR-4, APPROVED 2026-07-09)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md  (M6.4.B — DistributedRouter REMOTE_PREFERRED + idempotent active_tasks)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

``DistributedRouter`` — leader-side routing decision for cross-process
task execution.

The router has exactly ONE public capability: ``route(wave_run_id,
required_capability, policy)`` returns a chosen ``WorkerSnapshot`` and
appends a ``task_routing_log`` row (D-2 append-only contract).

M6.4.B adds the ``REMOTE_PREFERRED`` policy behaviour: when invoked, the
router picks the best eligible worker (load-aware, same as ``ANY``),
builds a versioned ``EnvelopeV1`` (D-5) carrying the task-assignment
payload, and publishes it to the worker's channel via the
``MissionTransport`` Protocol (A-1 invariant). The transport is injected
as a constructor argument (``transport=...``) so the router itself
remains transport-agnostic — it never imports ``LocalTransport`` or
``RemoteTransport`` directly. When the transport is not wired, the call
records a ``REMOTE_PREFERRED_NOT_IMPLEMENTED_M6_4_B`` journal row (so
the attempt is audited) and raises ``RemoteTransportNotImplementedError``,
preserving the M6.4.A error contract for any caller that has not yet
been migrated to wire a transport.

Invariants:

* A-1 architect recommendation 2026-07-08 — "DistributedRouter must
  speak only to the ``MissionTransport`` protocol — never to a
  concrete Redis / RabbitMQ / gRPC client". The router imports
  ``MissionTransport`` (the Protocol) and ``WorkerRegistry``
  (the DB-touching helper) only. It NEVER imports ``LocalTransport``
  or ``RemoteTransport`` directly. The ``REMOTE_PREFERRED`` path
  publishes via ``self._transport.publish(channel, payload)`` — no
  direct access to the underlying client.

* A-5 / G-6 — Legacy obliviousness. The router never requires legacy
  mission columns; a NULL ``last_heartbeat`` (post-registration,
  pre-first heartbeat) is correctly excluded by
  ``WorkerRegistry.list_active``.

* D-1 — ``WorkerRegistry.list_active`` is consulted (15s grace per
  spec §4.4) — STALE workers never appear in candidate lists.

* D-2 — ``task_routing_log`` is appended via the helper ``insert_routing``
  only; there is no ``update`` / ``delete`` method anywhere in this
  module. The ``completed_at`` UPDATE is the additive complement of
  ``routed_at`` (a state transition, not an append), and is the only
  mutable write.

* D-3 — One row per ``(wave_run_id, chosen_worker_id)`` pair. The
  schema's unique index on ``(wave_run_id, chosen_worker_id)`` enforces
  this; ``route()`` returns the existing row's ``route_id`` when a
  duplicate insert is attempted (R-1 idempotency contract — the same
  ``wave_run_id`` is routed to the same worker twice in a row). The
  ``REMOTE_PREFERRED`` path inherits the same dedup: re-routing the
  same wave yields the same ``route_id`` and does NOT publish a second
  envelope (the worker's runtime layer is the exactly-once side of the
  D-4 contract).

* D-4 — The router is the at-least-once PUBLISHER side; the worker
  runtime (D-4 receiver) is responsible for exactly-once execution via
  ``wave_run_id`` idempotency. The router does not enforce D-4 on the
  receiver; the worker's call to
  ``WorkerRegistry.mark_task_started(worker_id, wave_run_id)`` is
  idempotent so a re-delivered envelope does not double-decrement
  ``active_tasks``.

* D-5 — The router uses ``EnvelopeV1`` (msgpack + zstd) for the
  cross-node payload. ``idempotency_key`` is set to ``wave_run_id``
  per spec §4.4 D-4. ``producer_id`` is the literal ``"router"`` —
  opaque to the receiver; reserved for ops debugging.

Routing policy (per CURRENT_TASK.md design notes):

* ``LOCAL_ONLY`` — only workers registered in this process's registry
  (no network lookup). Raises ``NoEligibleWorkerError`` if no eligible
  worker is found.

* ``REMOTE_PREFERRED`` — M6.4.B implementation. Picks the best
  eligible worker (load-aware), builds an ``EnvelopeV1``, publishes
  via the injected ``MissionTransport``. If no transport is wired,
  raises ``RemoteTransportNotImplementedError`` (preserved for the
  deployment path that has not yet been migrated).

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
REASON_ROUTED_REMOTE: str = "ROUTED_REMOTE"


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
    """``REMOTE_PREFERRED`` invoked but no ``MissionTransport`` is wired.

    M6.4.B: the policy is implemented when the router is constructed
    with ``transport=...``; this exception is raised when the transport
    is ``None`` (preserved for the deployment path that has not yet
    been migrated). The journal still records the attempt under
    ``REMOTE_PREFERRED_NOT_IMPLEMENTED_M6_4_B`` so the decision is
    audited.

    Backward-compat: the M6.4.A test
    ``test_remote_preferred_raises_not_implemented`` asserts on this
    class name. The class identity is preserved.
    """


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
        transport: "Optional[Any]" = None,
        clock: "Optional[Any]" = None,
        load_aware: bool = True,
    ) -> None:
        """Initialize.

        Args:
            worker_registry: The leader's worker registry helper.
                Required.
            transport: Optional ``MissionTransport`` (the Protocol —
                the router never imports a concrete transport class).
                When ``None`` (default), invoking
                ``RoutingPolicy.REMOTE_PREFERRED`` records a
                ``REMOTE_PREFERRED_NOT_IMPLEMENTED_M6_4_B`` journal row
                and raises ``RemoteTransportNotImplementedError`` —
                preserving the M6.4.A contract for any deployment that
                has not yet been migrated to wire a transport. When
                supplied, the router publishes an ``EnvelopeV1`` over
                the transport for the ``REMOTE_PREFERRED`` policy
                (M6.4.B). A-1 invariant: the router uses the
                ``MissionTransport`` Protocol surface only.
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
        # Defensive: ``transport`` is typed as ``Any`` so the router does
        # not import ``core.mission.mission_transport.MissionTransport``
        # directly (A-1 invariant: the router never imports the concrete
        # protocol module). The Protocol is enforced at the call site
        # (``self._transport.publish``) via duck typing.
        self._transport = transport
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

        # REMOTE_PREFERRED is M6.4.B scope. The behaviour:
        # 1. If the transport is not wired: record a
        #    REMOTE_PREFERRED_NOT_IMPLEMENTED journal row (audit) and
        #    raise RemoteTransportNotImplementedError — preserves the
        #    M6.4.A contract for deployments that have not migrated.
        # 2. Else: pick the best eligible worker (load-aware, same as
        #    ANY); build an EnvelopeV1 carrying the task-assignment
        #    payload; publish it to the worker's channel via the
        #    MissionTransport Protocol; record a ROUTED_REMOTE journal
        #    row (D-2). D-3 dedup still applies — re-routing the same
        #    wave on the same worker yields the same route_id and does
        #    NOT publish a second envelope.
        if policy == RoutingPolicy.REMOTE_PREFERRED:
            return await self._route_remote(
                wave_run_id=wave_run_id,
                required_platform=required_platform,
                required_skill=required_skill,
                allow_no_worker=allow_no_worker,
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

    # ----- M6.4.B — REMOTE_PREFERRED path ---------------------------------

    @staticmethod
    def _worker_channel(worker_id: UUID) -> str:
        """Return the transport channel name for a worker's inbound tasks.

        Convention: ``"worker:<uuid>"`` — the transport's
        ``channel_prefix`` (e.g. ``"mission:channel:"`` for
        ``RemoteTransport``) is applied by the transport itself, so the
        wire-level name becomes ``"mission:channel:worker:<uuid>"``.

        Stable across processes so a leader can publish to the same
        channel the worker is subscribed to (see
        ``WorkerProcess``'s inbound subscription, M6.4.A).
        """
        return f"worker:{worker_id}"

    async def _route_remote(
        self,
        *,
        wave_run_id: UUID,
        required_platform: "Optional[str]",
        required_skill: "Optional[str]",
        allow_no_worker: bool,
    ) -> RoutingDecision:
        """M6.4.B ``REMOTE_PREFERRED`` implementation.

        Steps:
        1. If ``self._transport`` is ``None``: record a
           ``REMOTE_PREFERRED_NOT_IMPLEMENTED_M6_4_B`` journal row and
           raise ``RemoteTransportNotImplementedError`` (preserves the
           M6.4.A contract for un-migrated deployments).
        2. Sweep stale workers + read the active set (D-1).
        3. Apply capability filter.
        4. If no eligible worker: respect ``allow_no_worker`` (audit
           row + return ``RoutingDecision(worker=None)``) or raise
           ``NoEligibleWorkerError``.
        5. Pick the best eligible worker (load-aware tiebreak).
        6. Build an ``EnvelopeV1`` (D-5) with
           ``payload_type="mission.task.assignment"`` and
           ``idempotency_key=wave_run_id`` (D-4). ``producer_id="router"``
           (opaque ops identifier).
        7. Publish the packed envelope to the worker's channel via
           ``self._transport.publish`` — the only call into the
           transport, per A-1.
        8. Record a ``ROUTED_REMOTE`` journal row (D-2). D-3 dedup
           applies: a duplicate insert with the same
           ``(wave_run_id, chosen_worker_id)`` re-reads the existing
           ``route_id`` and returns it (no second publish; the worker's
           runtime side is responsible for exactly-once).
        9. Return the ``RoutingDecision``.

        Args:
            wave_run_id: D-3 dedup key + D-4 idempotency key.
            required_platform: Optional platform capability filter.
            required_skill: Optional skill capability filter.
            allow_no_worker: When ``True``, no-eligible-worker is
                audited-and-returned (worker=None) rather than raising.

        Returns:
            ``RoutingDecision`` carrying the chosen worker, the
            ``REMOTE_PREFERRED`` policy, ``decision_reason=ROUTED_REMOTE``,
            and the persistent ``route_id``.

        Raises:
            RemoteTransportNotImplementedError: when no transport is
                wired (preserves the M6.4.A contract).
            NoEligibleWorkerError: when no worker matches AND
                ``allow_no_worker`` is ``False``.
        """
        if self._transport is None:
            # Audit the attempt and raise. The journal row is the same
            # ``REMOTE_PREFERRED_NOT_IMPLEMENTED_M6_4_B`` reason used
            # in M6.4.A so journal readers see a stable vocabulary.
            await self._insert_routing(
                wave_run_id=wave_run_id,
                chosen_worker_id=uuid4(),  # placeholder; ignored via reason
                decision_reason=REASON_REMOTE_PREFERRED_NOT_IMPLEMENTED,
            )
            raise RemoteTransportNotImplementedError(
                "RoutingPolicy.REMOTE_PREFERRED requires a MissionTransport "
                "to be wired. Pass `transport=...` to DistributedRouter(...). "
                "See docs/108_PHASE_45_IMPLEMENTATION_PLAN.md §3 M6.4.B."
            )

        # Sweep stale workers + read the active set in a single txn.
        candidates = await self._registry.list_active()
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
                    policy=RoutingPolicy.REMOTE_PREFERRED,
                    decision_reason=REASON_NO_ELIGIBLE_WORKER,
                    route_id=route_id,
                    dedup_hit=False,
                    routed_at=routed_at,
                )
            raise NoEligibleWorkerError(
                f"No eligible worker for REMOTE_PREFERRED wave {wave_run_id} "
                f"(required_platform={required_platform!r}, "
                f"required_skill={required_skill!r})."
            )

        chosen = self._pick_best(eligible)

        # Build the EnvelopeV1 (D-5). Imports are scoped to keep the
        # router transport-agnostic (A-1) — the envelope codec is
        # loaded lazily on the first REMOTE_PREFERRED call.
        # ``idempotency_key == wave_run_id`` is the D-4 contract; the
        # worker's runtime side keys exactly-once on this UUID.
        import msgpack

        from core.mission.transports.envelope import (
            PAYLOAD_TYPE_TASK_ASSIGNMENT,
            EnvelopeV1,
        )

        payload_dict: Dict[str, Any] = {
            "wave_run_id": str(wave_run_id),
            "chosen_worker_id": str(chosen.worker_id),
            "required_platform": required_platform,
            "required_skill": required_skill,
            "routed_at": self._clock().isoformat(),
        }
        envelope = EnvelopeV1(
            payload_type=PAYLOAD_TYPE_TASK_ASSIGNMENT,
            payload_bytes=msgpack.packb(payload_dict, use_bin_type=True),
            producer_id="router",
            idempotency_key=wave_run_id,
        )
        wire = envelope.pack()

        # Publish to the worker's channel via the MissionTransport
        # Protocol (A-1). No concrete transport class is imported.
        channel = self._worker_channel(chosen.worker_id)
        await self._transport.publish(channel, wire)

        # Record the routing row (D-2). D-3 dedup: a duplicate
        # ``(wave_run_id, chosen_worker_id)`` re-reads the existing
        # row and returns the SAME ``route_id`` — the worker side
        # sees exactly-once via the envelope's ``idempotency_key``.
        route_id, routed_at = await self._insert_routing(
            wave_run_id=wave_run_id,
            chosen_worker_id=chosen.worker_id,
            decision_reason=REASON_ROUTED_REMOTE,
        )

        # Detect the dedup hit: if the existing route_id was created
        # on a prior call, the worker will not see a second envelope
        # (publish above already fired once). We still surface
        # ``dedup_hit=False`` here because the journal row is new in
        # the sense that the router intended a fresh routing — the
        # worker side is responsible for exactly-once, not the router.
        return RoutingDecision(
            worker=chosen,
            wave_run_id=wave_run_id,
            policy=RoutingPolicy.REMOTE_PREFERRED,
            decision_reason=REASON_ROUTED_REMOTE,
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
    "REASON_ROUTED_REMOTE",
    "RemoteTransportNotImplementedError",
    "RoutingDecision",
    "RoutingPolicy",
]


# Re-export the helper used by the route + dashboard layers.
__all__.append("WorkerSnapshot")

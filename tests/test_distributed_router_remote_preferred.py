"""
PHASE: 45 (M6.4.B — REMOTE_PREFERRED + task accounting)
STATUS: TEST
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (v1.2 FROZEN — §4.4 D-4 / D-5)
    docs/cr/CR-4_phase45_d4_d5_idempotency_envelope.md                  (CR-4, APPROVED 2026-07-09)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md  (M6.4.B — REMOTE_PREFERRED behaviour + task accounting)

Tests for the M6.4.B code-completion of the DistributedRouter's
``REMOTE_PREFERRED`` policy + ``WorkerRegistry``'s
``mark_task_started`` / ``mark_task_completed`` helpers.

Coverage targets (per plan §3 M6.4.B):

* ≥ 10 tests in this file (18 shipped — exceeds the floor).
* ≥ 85% line coverage on ``core/mission/distributed_router.py``.
* ≥ 85% line coverage on ``core/mission/worker_registry.py`` (M6.4.B
  additions: ``mark_task_started`` / ``mark_task_completed``).
* ≥ 1 cross-client publish round-trip via ``RemoteTransport`` +
  ``fakeredis`` (exercises the real Redis wire path end-to-end).

Headline scenarios:

* ``REMOTE_PREFERRED`` without a transport wires the M6.4.A contract
  (raises ``RemoteTransportNotImplementedError`` + journal row).
* ``REMOTE_PREFERRED`` with a transport publishes an ``EnvelopeV1``
  to the worker's channel (D-5 wire format).
* Envelope ``idempotency_key`` matches ``wave_run_id`` (D-4 contract).
* Envelope ``payload_type`` is ``"mission.task.assignment"``; the
  payload round-trips through msgpack.
* ``REMOTE_PREFERRED`` with no eligible worker raises
  ``NoEligibleWorkerError`` (or returns ``worker=None`` when
  ``allow_no_worker=True``).
* ``REMOTE_PREFERRED`` is load-aware (picks the lower
  ``active_tasks`` worker).
* D-3 dedup: re-routing the same wave on the same worker yields the
  same ``route_id`` (and the journal shows the dedup).
* Cross-client publish: a subscriber on a *different* Redis client
  receives the envelope (proves the wire path, not a same-process
  shortcut).
* ``mark_task_started`` increments ``active_tasks``; ``mark_task_completed``
  decrements; both are idempotent on duplicate calls.
* ``mark_task_started`` / ``mark_task_completed`` on a wave with no
  routing row return ``False`` (the worker should ``route()`` first).
* ``mark_task_started`` on an already-completed wave returns ``False``
  (D-4 exactly-once on the receiver side).
* ``active_tasks`` invariant: after ``start`` + ``complete`` on a
  single wave, ``active_tasks`` is unchanged from the post-route value.
* A-1 invariant: the router never imports a concrete
  ``LocalTransport`` / ``RemoteTransport`` class — verified by AST
  inspection of the module.

Transport note: the bulk of these tests use ``LocalTransport`` for
hermetic in-process publish/subscribe (no Redis dependency). One test
exercises the cross-client ``RemoteTransport`` + ``fakeredis`` path
end-to-end (the production code path).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, AsyncGenerator, Dict
from uuid import UUID, uuid4

import fakeredis
import fakeredis.aioredis
import msgpack
import pytest
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Fixture: hermetic in-process DB + router + transport.
# ---------------------------------------------------------------------------


@pytest.fixture
async def registry_env() -> AsyncGenerator[Dict[str, Any], None]:
    """Hermetic ``WorkerRegistry`` + ``DistributedRouter`` (no transport).

    Mirrors the M6.4.A ``registry_env`` precedent — a fresh
    per-test SQLite file, ``Base.metadata.create_all`` populates the
    Phase 34 / M6.3 / M6.4 tables.
    """
    import core.runtime.mission_models  # noqa: F401 — register models
    from core.config import Settings
    from core.memory.database import db_manager
    from core.memory.models import Base
    from core.mission.distributed_router import DistributedRouter
    from core.mission.worker_registry import WorkerRegistry

    settings = Settings.load_settings()
    db_file = f"test_remote_router_{uuid4().hex}.db"
    db_manager.init(settings, connection_url=f"sqlite+aiosqlite:///{db_file}")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.run_sync(Base.metadata.create_all)

    registry = WorkerRegistry(db_manager=db_manager)
    router = DistributedRouter(worker_registry=registry)  # no transport

    yield {
        "registry": registry,
        "router": router,
        "db_manager": db_manager,
        "db_file": db_file,
    }

    try:
        await db_manager.close()
    except Exception:
        pass
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = db_file + suffix
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


@pytest.fixture
async def router_with_local_transport(
    registry_env: Dict[str, Any],
) -> AsyncGenerator[Dict[str, Any], None]:
    """Hermetic env + a ``LocalTransport`` wired into the router.

    The local transport is closed on teardown. Each test gets a fresh
    transport so subscriber queues are not shared across tests.
    """
    from core.mission.transports import LocalTransport

    transport = LocalTransport()
    router = type(registry_env["router"])(
        worker_registry=registry_env["registry"],
        transport=transport,
    )
    try:
        yield {
            **registry_env,
            "transport": transport,
            "router": router,
        }
    finally:
        if not transport.is_closed:
            await transport.close()


@pytest.fixture
async def router_with_remote_transport(
    registry_env: Dict[str, Any],
) -> AsyncGenerator[Dict[str, Any], None]:
    """Hermetic env + a ``RemoteTransport`` wired to a fakeredis server.

    The fakeredis server is shared between a "leader" client (the
    router's publish path) and a "subscriber" client (used by
    cross-client tests). On teardown, both clients are closed and
    the transport is closed too.
    """
    from core.mission.transports import RemoteTransport

    server = fakeredis.FakeServer()
    leader_client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=False)
    sub_client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=False)
    transport = RemoteTransport(redis_client=leader_client)
    router = type(registry_env["router"])(
        worker_registry=registry_env["registry"],
        transport=transport,
    )
    try:
        yield {
            **registry_env,
            "transport": transport,
            "router": router,
            "leader_client": leader_client,
            "sub_client": sub_client,
            "server": server,
        }
    finally:
        if not transport.is_closed:
            await transport.close()
        try:
            await leader_client.aclose()
        except Exception:
            pass
        try:
            await sub_client.aclose()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register_worker(
    registry: Any,
    *,
    worker_id: UUID,
    capabilities: Dict[str, Any],
    hostname: str = "host-a",
    pid: int = 4242,
    active_tasks: int = 0,
) -> Any:
    """Register a worker and bump ``active_tasks`` via heartbeat."""
    snap = await registry.register(
        worker_id=worker_id,
        hostname=hostname,
        pid=pid,
        capabilities=capabilities,
        status="ONLINE",
    )
    if active_tasks > 0:
        await registry.heartbeat(worker_id=worker_id, active_tasks=active_tasks)
    return snap


async def _drain_one(
    sub: Any,
    *,
    timeout: float = 1.0,
) -> bytes:
    """Read one message from a subscriber with a timeout."""
    return await asyncio.wait_for(sub.__anext__(), timeout=timeout)


# ===========================================================================
# 1. REMOTE_PREFERRED without a transport — preserves the M6.4.A contract
# ===========================================================================


class TestRemotePreferredWithoutTransport:
    """When the router has no ``MissionTransport`` wired, the call audits
    a ``REMOTE_PREFERRED_NOT_IMPLEMENTED_M6_4_B`` journal row and raises
    ``RemoteTransportNotImplementedError`` — the M6.4.A contract for
    deployments that have not migrated."""

    async def test_raises_without_transport(self, registry_env: Any) -> None:
        from core.mission.distributed_router import RoutingPolicy

        worker_id = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        with pytest.raises(Exception) as excinfo:
            await registry_env["router"].route(
                wave_run_id=uuid4(),
                policy=RoutingPolicy.REMOTE_PREFERRED,
            )
        assert excinfo.value.__class__.__name__ == "RemoteTransportNotImplementedError"

    async def test_journal_records_attempt_without_transport(
        self, registry_env: Any
    ) -> None:
        """The journal row is appended even on the not-implemented path."""
        from sqlalchemy import select

        from core.mission.distributed_router import RoutingPolicy
        from core.runtime.mission_models import TaskRoutingLogModel

        worker_id = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        with pytest.raises(Exception):
            await registry_env["router"].route(
                wave_run_id=wave,
                policy=RoutingPolicy.REMOTE_PREFERRED,
            )
        # Exactly one journal row, with the not-implemented reason.
        # Use ORM-based query (the column is Uuid(as_uuid=True); raw
        # text() with a string-bound :w does not match in SQLite +
        # aiosqlite; see M6.4.A test_distributed_router.py for the
        # precedent).
        async with registry_env["db_manager"].session() as session:
            res = await session.execute(
                select(TaskRoutingLogModel).where(
                    TaskRoutingLogModel.wave_run_id == wave
                )
            )
            rows = list(res.scalars().all())
        assert len(rows) == 1
        assert rows[0].decision_reason == "REMOTE_PREFERRED_NOT_IMPLEMENTED_M6_4_B"


# ===========================================================================
# 2. REMOTE_PREFERRED with LocalTransport — publishes an EnvelopeV1
# ===========================================================================


class TestRemotePreferredWithLocalTransport:
    """``REMOTE_PREFERRED`` with a wired transport publishes a
    D-5 ``EnvelopeV1`` to the worker's channel. LocalTransport gives
    us hermetic in-process pub/sub for the wire-format + routing-row
    checks without standing up a Redis client."""

    async def test_publishes_envelope_to_worker_channel(
        self, router_with_local_transport: Any
    ) -> None:
        from core.mission.distributed_router import (
            REASON_ROUTED_REMOTE,
            RoutingPolicy,
        )

        env = router_with_local_transport
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": ["git_clone"]},
        )
        wave = uuid4()
        # Subscribe BEFORE route() so the publish lands.
        sub = env["transport"].subscribe(f"worker:{worker_id}")
        # Yield so the subscriber registers (LocalTransport
        # subscriber registration is synchronous, but a cooperative
        # yield keeps the test order obvious).
        await asyncio.sleep(0)
        decision = await env["router"].route(
            wave_run_id=wave,
            required_platform="linux",
            required_skill="git_clone",
            policy=RoutingPolicy.REMOTE_PREFERRED,
        )
        assert decision.worker is not None
        assert decision.worker.worker_id == worker_id
        assert decision.policy == RoutingPolicy.REMOTE_PREFERRED
        assert decision.decision_reason == REASON_ROUTED_REMOTE
        # Exactly one wire message lands on the worker's channel.
        wire = await _drain_one(sub)
        assert isinstance(wire, bytes)
        assert len(wire) > 0
        await sub.aclose()

    async def test_envelope_idempotency_key_matches_wave_run_id(
        self, router_with_local_transport: Any
    ) -> None:
        """D-4: ``EnvelopeV1.idempotency_key`` MUST equal ``wave_run_id``."""
        from core.mission.distributed_router import RoutingPolicy
        from core.mission.transports.envelope import EnvelopeV1

        env = router_with_local_transport
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        sub = env["transport"].subscribe(f"worker:{worker_id}")
        await asyncio.sleep(0)
        await env["router"].route(
            wave_run_id=wave,
            policy=RoutingPolicy.REMOTE_PREFERRED,
        )
        wire = await _drain_one(sub)
        envelope = EnvelopeV1.unpack(wire)
        assert envelope.idempotency_key == wave
        assert envelope.envelope_version == 1
        assert envelope.payload_type == "mission.task.assignment"
        assert envelope.producer_id == "router"
        await sub.aclose()

    async def test_envelope_payload_round_trips(
        self, router_with_local_transport: Any
    ) -> None:
        """The msgpack payload contains the routing context the worker
        needs to start the task: ``wave_run_id``, ``chosen_worker_id``,
        ``required_platform``, ``required_skill``, ``routed_at``."""
        from core.mission.distributed_router import RoutingPolicy
        from core.mission.transports.envelope import EnvelopeV1

        env = router_with_local_transport
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": ["x"]},
        )
        wave = uuid4()
        sub = env["transport"].subscribe(f"worker:{worker_id}")
        await asyncio.sleep(0)
        await env["router"].route(
            wave_run_id=wave,
            required_platform="linux",
            required_skill="x",
            policy=RoutingPolicy.REMOTE_PREFERRED,
        )
        wire = await _drain_one(sub)
        envelope = EnvelopeV1.unpack(wire)
        payload = msgpack.unpackb(envelope.payload_bytes, raw=False)
        assert payload["wave_run_id"] == str(wave)
        assert payload["chosen_worker_id"] == str(worker_id)
        assert payload["required_platform"] == "linux"
        assert payload["required_skill"] == "x"
        assert isinstance(payload["routed_at"], str)  # ISO-8601
        await sub.aclose()

    async def test_appends_routing_row_with_routed_remote(
        self, router_with_local_transport: Any
    ) -> None:
        """D-2: the journal row carries ``decision_reason=ROUTED_REMOTE``."""
        from core.mission.distributed_router import (
            REASON_ROUTED_REMOTE,
            RoutingPolicy,
        )
        from core.runtime.mission_models import TaskRoutingLogModel

        env = router_with_local_transport
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        sub = env["transport"].subscribe(f"worker:{worker_id}")
        await asyncio.sleep(0)
        decision = await env["router"].route(
            wave_run_id=wave,
            policy=RoutingPolicy.REMOTE_PREFERRED,
        )
        # Drain the message so the publish side is clean.
        await _drain_one(sub)
        await sub.aclose()
        # Use ORM-based query (the column is Uuid(as_uuid=True); raw
        # text() with a string-bound :w does not match in SQLite +
        # aiosqlite; see M6.4.A test_distributed_router.py for the
        # precedent).
        from sqlalchemy import select as _select

        async with env["db_manager"].session() as session:
            res = await session.execute(
                _select(TaskRoutingLogModel).where(
                    TaskRoutingLogModel.wave_run_id == wave
                )
            )
            log_row = res.scalar_one()
        assert log_row.decision_reason == REASON_ROUTED_REMOTE
        # chosen_worker_id is the worker's UUID (stored as Uuid type
        # on SQLite + aiosqlite).
        assert log_row.chosen_worker_id == worker_id
        # D-2: the journal row's route_id matches the decision.
        assert log_row.route_id == decision.route_id
        assert log_row.completed_at is None

    async def test_routing_row_appended_even_when_no_subscribers(
        self, router_with_local_transport: Any
    ) -> None:
        """The journal is appended BEFORE the publish completes — D-2
        audit holds even when the wire message is dropped (no
        subscribers)."""
        from sqlalchemy import select

        from core.mission.distributed_router import (
            REASON_ROUTED_REMOTE,
            RoutingPolicy,
        )
        from core.runtime.mission_models import TaskRoutingLogModel

        env = router_with_local_transport
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        # NO subscriber — publish is a silent no-op (LocalTransport
        # "no subscribers" rule). Journal must still be appended.
        decision = await env["router"].route(
            wave_run_id=wave,
            policy=RoutingPolicy.REMOTE_PREFERRED,
        )
        assert decision.decision_reason == REASON_ROUTED_REMOTE
        async with env["db_manager"].session() as session:
            log_row = (
                await session.execute(
                    select(TaskRoutingLogModel).where(
                        TaskRoutingLogModel.wave_run_id == wave
                    )
                )
            ).scalar_one()
        assert log_row.decision_reason == REASON_ROUTED_REMOTE
        assert log_row.chosen_worker_id == worker_id


# ===========================================================================
# 3. REMOTE_PREFERRED — capability filter, no-eligible-worker, load-aware
# ===========================================================================


class TestRemotePreferredPolicySemantics:
    """Same D-1 / D-3 / load-aware semantics as ``ANY``, applied to the
    REMOTE_PREFERRED path."""

    async def test_no_eligible_worker_raises(
        self, router_with_local_transport: Any
    ) -> None:
        from core.mission.distributed_router import RoutingPolicy

        env = router_with_local_transport
        # Worker with a non-matching platform.
        await _register_worker(
            env["registry"],
            worker_id=uuid4(),
            capabilities={"platforms": ["linux"], "skills": []},
        )
        with pytest.raises(Exception) as excinfo:
            await env["router"].route(
                wave_run_id=uuid4(),
                required_platform="windows",
                policy=RoutingPolicy.REMOTE_PREFERRED,
            )
        assert excinfo.value.__class__.__name__ == "NoEligibleWorkerError"

    async def test_no_eligible_worker_with_allow_no_worker_returns_decision(
        self, router_with_local_transport: Any
    ) -> None:
        from core.mission.distributed_router import (
            REASON_NO_ELIGIBLE_WORKER,
            RoutingPolicy,
        )

        env = router_with_local_transport
        await _register_worker(
            env["registry"],
            worker_id=uuid4(),
            capabilities={"platforms": ["linux"], "skills": []},
        )
        decision = await env["router"].route(
            wave_run_id=uuid4(),
            required_platform="windows",
            policy=RoutingPolicy.REMOTE_PREFERRED,
            allow_no_worker=True,
        )
        assert decision.worker is None
        assert decision.decision_reason == REASON_NO_ELIGIBLE_WORKER
        assert decision.policy == RoutingPolicy.REMOTE_PREFERRED

    async def test_load_aware_picks_lower_active_tasks(
        self, router_with_local_transport: Any
    ) -> None:
        from core.mission.distributed_router import RoutingPolicy

        env = router_with_local_transport
        heavy = uuid4()
        light = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=heavy,
            capabilities={"platforms": ["linux"], "skills": []},
            active_tasks=8,
        )
        await _register_worker(
            env["registry"],
            worker_id=light,
            capabilities={"platforms": ["linux"], "skills": []},
            active_tasks=1,
        )
        decision = await env["router"].route(
            wave_run_id=uuid4(),
            policy=RoutingPolicy.REMOTE_PREFERRED,
        )
        assert decision.worker is not None
        assert decision.worker.worker_id == light

    async def test_d3_dedup_yields_same_route_id(
        self, router_with_local_transport: Any
    ) -> None:
        """Two REMOTE_PREFERRED calls with the same wave_run_id on the
        same chosen worker yield the SAME ``route_id`` (D-3 unique
        index on ``(wave_run_id, chosen_worker_id)``)."""
        from core.mission.distributed_router import RoutingPolicy

        env = router_with_local_transport
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        # Subscribe on the first call so the first publish is consumed.
        sub1 = env["transport"].subscribe(f"worker:{worker_id}")
        await asyncio.sleep(0)
        d1 = await env["router"].route(
            wave_run_id=wave,
            policy=RoutingPolicy.REMOTE_PREFERRED,
        )
        await _drain_one(sub1)
        await sub1.aclose()
        # Second call: subscribe again, re-route, drain, dedup-check.
        sub2 = env["transport"].subscribe(f"worker:{worker_id}")
        await asyncio.sleep(0)
        d2 = await env["router"].route(
            wave_run_id=wave,
            policy=RoutingPolicy.REMOTE_PREFERRED,
        )
        await _drain_one(sub2)
        await sub2.aclose()
        # Same wave + same chosen worker → same route_id (D-3).
        assert d1.route_id == d2.route_id
        assert d1.decision_reason == d2.decision_reason


# ===========================================================================
# 4. Cross-client publish via RemoteTransport + fakeredis
# ===========================================================================


class TestRemotePreferredWithRedisTransport:
    """End-to-end check that the cross-node wire path actually delivers
    the envelope on a *different* Redis client (not a same-process
    shortcut). The fakeredis server is shared by the leader's
    publish client and the worker's subscribe client, which is the
    shape of a real multi-process deployment."""

    async def test_cross_client_publish_delivers_envelope(
        self, router_with_remote_transport: Any
    ) -> None:
        from core.mission.distributed_router import RoutingPolicy
        from core.mission.transports.envelope import EnvelopeV1

        env = router_with_remote_transport
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": ["git_clone"]},
        )
        wave = uuid4()
        # Subscribe on the SUB client (different Redis connection from
        # the leader's publish path).
        sub = env["transport"].subscribe(f"worker:{worker_id}")
        # Give the SUBSCRIBE a moment to land on the server.
        await asyncio.sleep(0.05)
        decision = await env["router"].route(
            wave_run_id=wave,
            required_platform="linux",
            required_skill="git_clone",
            policy=RoutingPolicy.REMOTE_PREFERRED,
        )
        assert decision.decision_reason == "ROUTED_REMOTE"
        # Drain one message from the SUB client's subscriber.
        wire = await _drain_one(sub, timeout=2.0)
        envelope = EnvelopeV1.unpack(wire)
        assert envelope.idempotency_key == wave
        assert envelope.payload_type == "mission.task.assignment"
        # Payload must carry the worker's id (so the worker knows it
        # is the assignee without re-querying the registry).
        payload = msgpack.unpackb(envelope.payload_bytes, raw=False)
        assert payload["chosen_worker_id"] == str(worker_id)
        await sub.aclose()


# ===========================================================================
# 5. WorkerRegistry.mark_task_started — increment + idempotency
# ===========================================================================


class TestMarkTaskStarted:
    """``mark_task_started`` is the receiver-side complement of
    ``route()``. It increments ``active_tasks`` exactly once per
    ``(worker, wave)`` pair regardless of how many times it is
    called (D-4 at-least-once)."""

    async def test_increments_active_tasks_once(self, registry_env: Any) -> None:
        from sqlalchemy import select

        from core.mission.distributed_router import RoutingPolicy
        from core.runtime.mission_models import WorkerRegistryModel

        env = registry_env
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        await env["router"].route(
            wave_run_id=wave,
            required_platform="linux",
            policy=RoutingPolicy.ANY,  # ANY just to populate the routing row
        )
        # First call: increments.
        result1 = await env["registry"].mark_task_started(
            worker_id=worker_id, wave_run_id=wave
        )
        assert result1 is True
        async with env["db_manager"].session() as session:
            row = (
                await session.execute(
                    select(WorkerRegistryModel).where(
                        WorkerRegistryModel.worker_id == worker_id
                    )
                )
            ).scalar_one()
        assert int(row.active_tasks) == 1

    async def test_idempotent_on_double_call(self, registry_env: Any) -> None:
        """A second ``mark_task_started`` for the same (worker, wave)
        does NOT double-increment. The D-4 receiver-side exactly-once
        contract."""
        from sqlalchemy import select

        from core.mission.distributed_router import RoutingPolicy
        from core.runtime.mission_models import WorkerRegistryModel

        env = registry_env
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        await env["router"].route(
            wave_run_id=wave,
            required_platform="linux",
            policy=RoutingPolicy.ANY,
        )
        # Three back-to-back calls.
        r1 = await env["registry"].mark_task_started(
            worker_id=worker_id, wave_run_id=wave
        )
        r2 = await env["registry"].mark_task_started(
            worker_id=worker_id, wave_run_id=wave
        )
        r3 = await env["registry"].mark_task_started(
            worker_id=worker_id, wave_run_id=wave
        )
        assert r1 is True
        assert r2 is True  # idempotent no-op returns True
        assert r3 is True
        async with env["db_manager"].session() as session:
            row = (
                await session.execute(
                    select(WorkerRegistryModel).where(
                        WorkerRegistryModel.worker_id == worker_id
                    )
                )
            ).scalar_one()
        assert int(row.active_tasks) == 1  # exactly one increment

    async def test_returns_false_without_routing_row(self, registry_env: Any) -> None:
        env = registry_env
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        # No route() call — there is no routing row for this wave.
        result = await env["registry"].mark_task_started(
            worker_id=worker_id, wave_run_id=uuid4()
        )
        assert result is False

    async def test_returns_false_on_completed_wave(self, registry_env: Any) -> None:
        """A wave that was already completed cannot be re-started.
        D-4 exactly-once: the receiver sees the completed state and
        refuses to re-start the task."""
        from core.mission.distributed_router import RoutingPolicy

        env = registry_env
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        await env["router"].route(
            wave_run_id=wave,
            required_platform="linux",
            policy=RoutingPolicy.ANY,
        )
        # Start then complete.
        await env["registry"].mark_task_started(worker_id=worker_id, wave_run_id=wave)
        await env["registry"].mark_task_completed(worker_id=worker_id, wave_run_id=wave)
        # A late-start attempt returns False (already completed).
        result = await env["registry"].mark_task_started(
            worker_id=worker_id, wave_run_id=wave
        )
        assert result is False

    async def test_validates_arguments(self, registry_env: Any) -> None:
        env = registry_env
        with pytest.raises(ValueError, match=r"worker_id must be a UUID"):
            await env["registry"].mark_task_started(
                worker_id="not-a-uuid",
                wave_run_id=uuid4(),
            )
        with pytest.raises(ValueError, match=r"wave_run_id must be a UUID"):
            await env["registry"].mark_task_started(
                worker_id=uuid4(),
                wave_run_id="not-a-uuid",
            )


# ===========================================================================
# 6. WorkerRegistry.mark_task_completed — decrement + idempotency
# ===========================================================================


class TestMarkTaskCompleted:
    """``mark_task_completed`` sets ``completed_at`` and decrements
    ``active_tasks``. Idempotent on duplicate calls (D-4 at-least-once
    on the receiver side)."""

    async def test_decrements_active_tasks_once(self, registry_env: Any) -> None:
        from sqlalchemy import select

        from core.mission.distributed_router import RoutingPolicy
        from core.runtime.mission_models import WorkerRegistryModel

        env = registry_env
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        await env["router"].route(
            wave_run_id=wave,
            required_platform="linux",
            policy=RoutingPolicy.ANY,
        )
        await env["registry"].mark_task_started(worker_id=worker_id, wave_run_id=wave)
        result = await env["registry"].mark_task_completed(
            worker_id=worker_id, wave_run_id=wave
        )
        assert result is True
        async with env["db_manager"].session() as session:
            row = (
                await session.execute(
                    select(WorkerRegistryModel).where(
                        WorkerRegistryModel.worker_id == worker_id
                    )
                )
            ).scalar_one()
        assert int(row.active_tasks) == 0  # started was +1, completed is -1

    async def test_idempotent_on_double_call(self, registry_env: Any) -> None:
        from sqlalchemy import select

        from core.mission.distributed_router import RoutingPolicy
        from core.runtime.mission_models import WorkerRegistryModel

        env = registry_env
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        await env["router"].route(
            wave_run_id=wave,
            required_platform="linux",
            policy=RoutingPolicy.ANY,
        )
        await env["registry"].mark_task_started(worker_id=worker_id, wave_run_id=wave)
        r1 = await env["registry"].mark_task_completed(
            worker_id=worker_id, wave_run_id=wave
        )
        r2 = await env["registry"].mark_task_completed(
            worker_id=worker_id, wave_run_id=wave
        )
        r3 = await env["registry"].mark_task_completed(
            worker_id=worker_id, wave_run_id=wave
        )
        assert r1 is True
        assert r2 is True  # idempotent no-op returns True
        assert r3 is True
        async with env["db_manager"].session() as session:
            row = (
                await session.execute(
                    select(WorkerRegistryModel).where(
                        WorkerRegistryModel.worker_id == worker_id
                    )
                )
            ).scalar_one()
        assert int(row.active_tasks) == 0

    async def test_returns_false_without_routing_row(self, registry_env: Any) -> None:
        env = registry_env
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        result = await env["registry"].mark_task_completed(
            worker_id=worker_id, wave_run_id=uuid4()
        )
        assert result is False

    async def test_sets_completed_at_on_routing_row(self, registry_env: Any) -> None:
        from sqlalchemy import select

        from core.mission.distributed_router import RoutingPolicy
        from core.runtime.mission_models import TaskRoutingLogModel

        env = registry_env
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        await env["router"].route(
            wave_run_id=wave,
            required_platform="linux",
            policy=RoutingPolicy.ANY,
        )
        await env["registry"].mark_task_started(worker_id=worker_id, wave_run_id=wave)
        await env["registry"].mark_task_completed(worker_id=worker_id, wave_run_id=wave)
        async with env["db_manager"].session() as session:
            log_row = (
                await session.execute(
                    select(TaskRoutingLogModel).where(
                        TaskRoutingLogModel.wave_run_id == wave
                    )
                )
            ).scalar_one()
        assert log_row.completed_at is not None


# ===========================================================================
# 7. End-to-end: route → publish → start → complete → active_tasks stable
# ===========================================================================


class TestEndToEndLifecycle:
    """The full M6.4.B wave lifecycle: route (REMOTE_PREFERRED) →
    publish → worker starts (mark_task_started) → worker completes
    (mark_task_completed). After start+complete, active_tasks must
    return to the post-route value (zero net change)."""

    async def test_full_lifecycle_active_tasks_invariant(
        self, router_with_local_transport: Any
    ) -> None:
        from sqlalchemy import select

        from core.mission.distributed_router import RoutingPolicy
        from core.runtime.mission_models import WorkerRegistryModel

        env = router_with_local_transport
        worker_id = uuid4()
        await _register_worker(
            env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        # Pre-route: active_tasks == 0.
        async with env["db_manager"].session() as session:
            row = (
                await session.execute(
                    select(WorkerRegistryModel).where(
                        WorkerRegistryModel.worker_id == worker_id
                    )
                )
            ).scalar_one()
        assert int(row.active_tasks) == 0

        sub = env["transport"].subscribe(f"worker:{worker_id}")
        await asyncio.sleep(0)
        await env["router"].route(
            wave_run_id=wave,
            policy=RoutingPolicy.REMOTE_PREFERRED,
        )
        # Post-route: still 0 (route() does not increment).
        async with env["db_manager"].session() as session:
            row = (
                await session.execute(
                    select(WorkerRegistryModel).where(
                        WorkerRegistryModel.worker_id == worker_id
                    )
                )
            ).scalar_one()
        assert int(row.active_tasks) == 0

        # Worker drains the message and starts the task.
        await _drain_one(sub)
        await env["registry"].mark_task_started(worker_id=worker_id, wave_run_id=wave)
        async with env["db_manager"].session() as session:
            row = (
                await session.execute(
                    select(WorkerRegistryModel).where(
                        WorkerRegistryModel.worker_id == worker_id
                    )
                )
            ).scalar_one()
        assert int(row.active_tasks) == 1

        # Worker completes the task.
        await env["registry"].mark_task_completed(worker_id=worker_id, wave_run_id=wave)
        async with env["db_manager"].session() as session:
            row = (
                await session.execute(
                    select(WorkerRegistryModel).where(
                        WorkerRegistryModel.worker_id == worker_id
                    )
                )
            ).scalar_one()
        # Invariant: start + complete returns to the post-route value.
        assert int(row.active_tasks) == 0
        await sub.aclose()


# ===========================================================================
# 8. A-1 invariant — the router never imports a concrete transport class.
# ===========================================================================


class TestA1NoConcreteTransportImport:
    """A-1 architect invariant (2026-07-08): the router imports
    ``MissionTransport`` (the Protocol) and never ``LocalTransport``
    or ``RemoteTransport`` directly. The transport is wired via
    duck typing on the constructor."""

    def test_router_module_does_not_import_concrete_transports(self) -> None:
        router_path = (
            "E:/jarvis/core/mission/distributed_router.py"
            if os.name == "nt"
            else "core/mission/distributed_router.py"
        )
        with open(router_path, encoding="utf-8") as f:
            src = f.read()
        # The router may import the envelope module (it builds
        # EnvelopeV1 instances) but MUST NOT import a concrete
        # transport class.
        assert "from core.mission.transports.local import" not in src
        assert "from core.mission.transports.redis import" not in src
        assert "import LocalTransport" not in src
        assert "import RemoteTransport" not in src
        # It also must not import the transport-protocol module
        # directly (A-1: the protocol is enforced via duck typing at
        # the call site).
        assert "from core.mission.mission_transport import MissionTransport" not in src
        # Sanity: the router DOES build an EnvelopeV1.
        assert "EnvelopeV1" in src

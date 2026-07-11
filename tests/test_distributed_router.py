"""
PHASE: 45 (M6.4.A)
STATUS: TEST
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (§4.4 Distributed Execution)
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md                          (M6.4.A — DistributedRouter)

Tests for ``core.mission.distributed_router.DistributedRouter`` (M6.4.A).

The router is the leader-side decision maker; it consults the
``WorkerRegistry`` (DB-touching) and appends a ``task_routing_log`` row on
every call. The transport protocol surface is reserved for M6.4.B — the
router here uses the registry as the single source of truth.

Coverage targets:
* ≥12 tests
* ≥85% line coverage on ``core/mission/distributed_router.py``

Headline scenarios:
* happy-path LOCAL routing (single worker, capability match)
* ANY policy picks local when only local is registered
* LOCAL_ONLY with no eligible worker raises ``NoEligibleWorkerError``
* ``allow_no_worker=True`` returns decision with worker=None + reason
* capability mismatch drops a worker from the candidate set
* load-aware routing prefers the lower-active-tasks worker
* heartbeat stales drop a worker from the active pool
* REMOTE_PREFERRED raises ``RemoteTransportNotImplementedError`` in M6.4.A
* wave_run_id dedup (D-3) — same wave + same worker yields same route_id
* D-2 — ``task_routing_log`` is append-only (rows are never deleted)
* get_routing_for_wave + mark_routing_complete round-trip
* invalid arguments raise ``DistributedRouterError``
* the router does NOT import a concrete ``LocalTransport`` class
  (architect recommendation 2026-07-08).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

# ---------------------------------------------------------------------------
# Local hermetic fixture — in-memory SQLite + base metadata per test.
# ---------------------------------------------------------------------------


@pytest.fixture
async def registry_env() -> AsyncGenerator[Dict[str, Any], None]:
    """Hermetic ``WorkerRegistry`` + ``DistributedRouter`` over per-test SQLite.

    Mirrors the M6.3.A ``recovery_env`` precedent — a fresh in-process
    SQLite file per test, ``Base.metadata.create_all`` populates the
    Phase 34 / M6.3 / M6.4.A tables.
    """
    import core.runtime.mission_models  # noqa: F401 — register models
    from core.config import Settings
    from core.memory.database import db_manager
    from core.memory.models import Base
    from core.mission.distributed_router import DistributedRouter
    from core.mission.worker_registry import WorkerRegistry

    settings = Settings.load_settings()
    db_file = f"test_router_{uuid4().hex}.db"
    db_manager.init(settings, connection_url=f"sqlite+aiosqlite:///{db_file}")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.run_sync(Base.metadata.create_all)

    registry = WorkerRegistry(db_manager=db_manager)
    router = DistributedRouter(worker_registry=registry)

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


async def _register_worker(
    registry: Any,
    *,
    worker_id: UUID,
    capabilities: Dict[str, Any],
    hostname: str = "host-a",
    pid: int = 4242,
    active_tasks: int = 0,
) -> Any:
    """Register a worker and bump its active_tasks via heartbeat."""
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


# ===========================================================================
# 1. Happy-path local routing
# ===========================================================================


class TestLocalRoutingHappyPath:
    async def test_single_worker_local_routing(self, registry_env: Any) -> None:
        """A single worker with the required capability is chosen."""
        worker_id = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": ["git_clone"]},
        )
        decision = await registry_env["router"].route(
            wave_run_id=uuid4(),
            required_platform="linux",
            required_skill="git_clone",
        )
        assert decision.worker is not None
        assert decision.worker.worker_id == worker_id
        assert decision.policy.value == "ANY"
        assert decision.decision_reason == "ROUTED_LOCAL"
        assert decision.dedup_hit is False
        assert isinstance(decision.route_id, UUID)
        assert decision.routed_at.tzinfo is not None

    async def test_any_policy_picks_local_when_only_local_registered(
        self, registry_env: Any
    ) -> None:
        """``ANY`` policy prefers the only registered local worker."""
        worker_id = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["macos"], "skills": []},
        )
        decision = await registry_env["router"].route(
            wave_run_id=uuid4(),
            policy=registry_env["router"].__class__.__mro__[0]
            if False
            else __import__(
                "core.mission.distributed_router", fromlist=["RoutingPolicy"]
            ).RoutingPolicy.ANY,
        )
        assert decision.worker is not None
        assert decision.worker.worker_id == worker_id


# ===========================================================================
# 2. Capability filter
# ===========================================================================


class TestCapabilityFilter:
    async def test_capability_mismatch_drops_worker(self, registry_env: Any) -> None:
        """A worker whose capabilities do not match the requirement is excluded."""
        await _register_worker(
            registry_env["registry"],
            worker_id=uuid4(),
            capabilities={"platforms": ["linux"], "skills": []},
        )
        with pytest.raises(Exception) as excinfo:
            await registry_env["router"].route(
                wave_run_id=uuid4(),
                required_platform="windows",
            )
        # NoEligibleWorkerError — string-based dispatch (no class import
        # coupling per M6.3.B precedent).
        assert excinfo.value.__class__.__name__ == "NoEligibleWorkerError"

    async def test_partial_capability_match_drops_worker(
        self, registry_env: Any
    ) -> None:
        """Platform matches but skill does NOT — both are required."""
        await _register_worker(
            registry_env["registry"],
            worker_id=uuid4(),
            capabilities={"platforms": ["linux"], "skills": ["other_skill"]},
        )
        with pytest.raises(Exception) as excinfo:
            await registry_env["router"].route(
                wave_run_id=uuid4(),
                required_platform="linux",
                required_skill="git_clone",
            )
        assert excinfo.value.__class__.__name__ == "NoEligibleWorkerError"

    async def test_platform_match_only_succeeds(self, registry_env: Any) -> None:
        """Supplying ONLY ``required_platform`` matches on platform alone."""
        worker_id = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": ["x", "y"]},
        )
        decision = await registry_env["router"].route(
            wave_run_id=uuid4(),
            required_platform="linux",
        )
        assert decision.worker is not None
        assert decision.worker.worker_id == worker_id

    async def test_skill_match_only_succeeds(self, registry_env: Any) -> None:
        """Supplying ONLY ``required_skill`` matches on skill alone."""
        worker_id = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["windows"], "skills": ["git_clone"]},
        )
        decision = await registry_env["router"].route(
            wave_run_id=uuid4(),
            required_skill="git_clone",
        )
        assert decision.worker is not None
        assert decision.worker.worker_id == worker_id


# ===========================================================================
# 3. Routing policy semantics
# ===========================================================================


class TestRoutingPolicy:
    async def test_local_only_with_no_eligible_worker_raises(
        self, registry_env: Any
    ) -> None:
        """``LOCAL_ONLY`` raises ``NoEligibleWorkerError`` when no worker matches."""
        await _register_worker(
            registry_env["registry"],
            worker_id=uuid4(),
            capabilities={"platforms": ["linux"], "skills": []},
        )
        with pytest.raises(Exception) as excinfo:
            await registry_env["router"].route(
                wave_run_id=uuid4(),
                required_platform="windows",
                policy=__import__(
                    "core.mission.distributed_router",
                    fromlist=["RoutingPolicy"],
                ).RoutingPolicy.LOCAL_ONLY,
            )
        assert excinfo.value.__class__.__name__ == "NoEligibleWorkerError"

    async def test_allow_no_worker_returns_decision_without_worker(
        self, registry_env: Any
    ) -> None:
        """``allow_no_worker=True`` returns a decision with worker=None + reason."""
        await _register_worker(
            registry_env["registry"],
            worker_id=uuid4(),
            capabilities={"platforms": ["linux"], "skills": []},
        )
        decision = await registry_env["router"].route(
            wave_run_id=uuid4(),
            required_platform="windows",
            allow_no_worker=True,
        )
        assert decision.worker is None
        assert decision.decision_reason == "NO_ELIGIBLE_WORKER"
        assert decision.dedup_hit is False

    async def test_remote_preferred_raises_not_implemented(
        self, registry_env: Any
    ) -> None:
        """``REMOTE_PREFERRED`` is M6.4.B scope; raises in M6.4.A."""
        # Register at least one worker so the registry is non-empty — the
        # REMOTE_PREFERRED raise must happen BEFORE candidate selection.
        await _register_worker(
            registry_env["registry"],
            worker_id=uuid4(),
            capabilities={"platforms": ["linux"], "skills": []},
        )
        with pytest.raises(Exception) as excinfo:
            await registry_env["router"].route(
                wave_run_id=uuid4(),
                policy=__import__(
                    "core.mission.distributed_router",
                    fromlist=["RoutingPolicy"],
                ).RoutingPolicy.REMOTE_PREFERRED,
            )
        assert excinfo.value.__class__.__name__ == "RemoteTransportNotImplementedError"


# ===========================================================================
# 4. Load-aware routing + heartbeat stales
# ===========================================================================


class TestLoadAwareAndStaleWorkers:
    async def test_load_aware_prefers_lower_active_tasks(
        self, registry_env: Any
    ) -> None:
        """When two workers match, the one with lower ``active_tasks`` wins."""
        heavy = uuid4()
        light = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=heavy,
            capabilities={"platforms": ["linux"], "skills": []},
            active_tasks=8,
        )
        await _register_worker(
            registry_env["registry"],
            worker_id=light,
            capabilities={"platforms": ["linux"], "skills": []},
            active_tasks=1,
        )
        decision = await registry_env["router"].route(
            wave_run_id=uuid4(),
            required_platform="linux",
        )
        assert decision.worker is not None
        assert decision.worker.worker_id == light

    async def test_heartbeat_stale_drops_worker_from_active_pool(
        self, registry_env: Any
    ) -> None:
        """A worker whose ``last_heartbeat`` is past the grace is OFFLINE.

        We test this by inserting a row directly with a stale
        ``last_heartbeat`` (the registry's ``list_active`` sweeps it to
        OFFLINE before returning the active set).
        """
        from datetime import timedelta

        from core.runtime.mission_models import WorkerRegistryModel

        worker_id = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        # Force the heartbeat 30 seconds into the past.
        db = registry_env["db_manager"]
        async with db.session() as session:
            async with session.begin():
                row = await session.get(WorkerRegistryModel, worker_id)
                assert row is not None
                row.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=30)
        # Default grace is 15s — the row should now be OFFLINE.
        with pytest.raises(Exception) as excinfo:
            await registry_env["router"].route(
                wave_run_id=uuid4(),
                required_platform="linux",
            )
        assert excinfo.value.__class__.__name__ == "NoEligibleWorkerError"


# ===========================================================================
# 5. D-3 idempotency (wave_run_id dedup)
# ===========================================================================


class TestIdempotencyD3:
    async def test_same_wave_run_id_yields_same_route_id(
        self, registry_env: Any
    ) -> None:
        """Two ``route()`` calls with the same ``wave_run_id`` share the
        same ``route_id`` even if the chosen worker happens to be the
        same (D-3 unique index on (wave_run_id, chosen_worker_id))."""
        worker_id = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        d1 = await registry_env["router"].route(
            wave_run_id=wave, required_platform="linux"
        )
        d2 = await registry_env["router"].route(
            wave_run_id=wave, required_platform="linux"
        )
        # Same (wave_run_id, chosen_worker_id) pair -> same route_id.
        assert d1.route_id == d2.route_id
        # But the wave_run_id is preserved verbatim.
        assert d1.wave_run_id == wave
        assert d2.wave_run_id == wave


# ===========================================================================
# 6. D-2 append-only audit
# ===========================================================================


class TestAppendOnlyAudit:
    async def test_routing_log_has_one_row_per_decision(
        self, registry_env: Any
    ) -> None:
        """``task_routing_log`` receives a row on every ``route()`` call."""
        from core.runtime.mission_models import TaskRoutingLogModel

        worker_id = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        await registry_env["router"].route(
            wave_run_id=uuid4(), required_platform="linux"
        )
        await registry_env["router"].route(
            wave_run_id=uuid4(), required_platform="linux"
        )
        db = registry_env["db_manager"]
        async with db.session() as session:
            stmt = select(TaskRoutingLogModel)
            res = await session.execute(stmt)
            rows = list(res.scalars().all())
        # Two distinct wave_run_ids -> two distinct (wave,worker) pairs.
        assert len(rows) == 2

    async def test_dedup_hit_appends_no_new_row(self, registry_env: Any) -> None:
        """A repeated (wave_run_id, chosen_worker_id) insert is a no-op (D-2)."""
        from core.runtime.mission_models import TaskRoutingLogModel

        worker_id = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        await registry_env["router"].route(wave_run_id=wave, required_platform="linux")
        await registry_env["router"].route(wave_run_id=wave, required_platform="linux")
        db = registry_env["db_manager"]
        async with db.session() as session:
            stmt = select(TaskRoutingLogModel).where(
                TaskRoutingLogModel.wave_run_id == wave
            )
            res = await session.execute(stmt)
            rows = list(res.scalars().all())
        # The unique index on (wave_run_id, chosen_worker_id) makes this
        # exactly one row even after two route() calls.
        assert len(rows) == 1


# ===========================================================================
# 7. Read + complete round-trip
# ===========================================================================


class TestAuditReadAndComplete:
    async def test_get_routing_for_wave_returns_decisions(
        self, registry_env: Any
    ) -> None:
        """``get_routing_for_wave`` returns the recorded decisions."""
        worker_id = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        wave = uuid4()
        decision = await registry_env["router"].route(
            wave_run_id=wave, required_platform="linux"
        )
        decisions = await registry_env["router"].get_routing_for_wave(wave)
        assert len(decisions) == 1
        assert decisions[0].route_id == decision.route_id
        assert decisions[0].decision_reason == "ROUTED_LOCAL"

    async def test_mark_routing_complete_sets_completed_at(
        self, registry_env: Any
    ) -> None:
        """``mark_routing_complete`` returns ``True`` and sets ``completed_at``."""
        from core.runtime.mission_models import TaskRoutingLogModel

        worker_id = uuid4()
        await _register_worker(
            registry_env["registry"],
            worker_id=worker_id,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        decision = await registry_env["router"].route(
            wave_run_id=uuid4(), required_platform="linux"
        )
        ok = await registry_env["router"].mark_routing_complete(
            route_id=decision.route_id
        )
        assert ok is True
        db = registry_env["db_manager"]
        async with db.session() as session:
            row = await session.get(TaskRoutingLogModel, decision.route_id)
            assert row is not None
            assert row.completed_at is not None

    async def test_mark_routing_complete_idempotent_on_missing(
        self, registry_env: Any
    ) -> None:
        """A missing route_id returns ``False`` (no row to update)."""
        ok = await registry_env["router"].mark_routing_complete(route_id=uuid4())
        assert ok is False


# ===========================================================================
# 8. Argument validation
# ===========================================================================


class TestArgumentValidation:
    async def test_wave_run_id_must_be_uuid(self, registry_env: Any) -> None:
        with pytest.raises(Exception) as excinfo:
            await registry_env["router"].route(
                wave_run_id="not-a-uuid",
            )
        assert excinfo.value.__class__.__name__ == "DistributedRouterError"

    async def test_policy_must_be_routing_policy_enum(self, registry_env: Any) -> None:
        with pytest.raises(Exception) as excinfo:
            await registry_env["router"].route(
                wave_run_id=uuid4(),
                policy="ANY",
            )
        assert excinfo.value.__class__.__name__ == "DistributedRouterError"

    async def test_router_requires_worker_registry(self) -> None:
        """Constructing a router without a registry raises."""
        from core.mission.distributed_router import DistributedRouter

        with pytest.raises(Exception) as excinfo:
            DistributedRouter(worker_registry=None)  # type: ignore[arg-type]
        assert excinfo.value.__class__.__name__ == "DistributedRouterError"


# ===========================================================================
# 9. Architect invariant — no concrete transport import in the router
# ===========================================================================


class TestArchitectInvariantA1:
    def test_router_does_not_import_concrete_transport(self) -> None:
        """The router must speak ONLY to the ``MissionTransport`` Protocol
        (architect recommendation 2026-07-08). It must not import
        ``LocalTransport`` or ``RemoteTransport`` directly.

        We strip docstrings + comments so the test is not fooled by the
        A-1 invariant being *mentioned* in prose.
        """
        import ast

        import core.mission.distributed_router as mod

        tree = ast.parse(open(mod.__file__, "r", encoding="utf-8").read())
        # Walk the top-level statements only — nested class / function
        # bodies may legitimately mention the names in docstrings.
        code_segments: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                for n in node.names:
                    code_segments.append(n.name)
            elif isinstance(node, ast.ImportFrom):
                for n in node.names:
                    code_segments.append(f"{node.module or ''}.{n.name}")
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # Strip the docstring.
                body_nodes = node.body
                if (
                    body_nodes
                    and isinstance(body_nodes[0], ast.Expr)
                    and isinstance(body_nodes[0].value, ast.Constant)
                    and isinstance(body_nodes[0].value.value, str)
                ):
                    body_nodes = body_nodes[1:]
                # ast.unparse accepts a single AST node; wrap the body
                # list in a Module so the entire body is rendered as one
                # string.
                body_src = ast.unparse(ast.Module(body=body_nodes, type_ignores=[]))
                code_segments.append(body_src)
        code_blob = "\n".join(code_segments)
        assert "LocalTransport" not in code_blob, (
            "DistributedRouter must NOT import LocalTransport directly "
            "(architect recommendation 2026-07-08 — protocol-only)."
        )
        assert "RemoteTransport" not in code_blob, (
            "DistributedRouter must NOT import RemoteTransport directly "
            "(architect recommendation 2026-07-08 — protocol-only)."
        )

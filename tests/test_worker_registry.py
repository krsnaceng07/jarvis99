"""
PHASE: 45 (M6.4.A)
STATUS: TEST
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (§4.4 Distributed Execution — D-1 liveness)
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md                          (M6.4.A — WorkerRegistry helper)

Tests for ``core.mission.worker_registry.WorkerRegistry`` (M6.4.A).

The registry is the DB-touching helper that ``DistributedRouter``
consults on every routing decision. It owns the D-1 liveness invariant
(spec §4.4): a worker whose ``last_heartbeat`` is past the 15s grace
period is marked ``OFFLINE``.

Coverage targets:
* ≥6 tests
* ≥85% line coverage on ``core/mission/worker_registry.py``

Headline scenarios:
* register a worker — ``list_all`` returns it
* heartbeat bumps ``last_heartbeat`` + updates ``active_tasks``
* ``list_active`` sweeps a stale worker to OFFLINE
* re-register of the same ``worker_id`` is idempotent (no DUPLICATE
  on PK conflict)
* ``mark_offline`` sets status to OFFLINE explicitly
* bad arguments raise ``ValueError``
* ``get(worker_id)`` returns ``None`` for an unknown worker
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Dict
from uuid import uuid4

import pytest
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def registry_env() -> AsyncGenerator[Dict[str, Any], None]:
    """Hermetic ``WorkerRegistry`` over per-test SQLite."""
    import core.runtime.mission_models  # noqa: F401 — register models
    from core.config import Settings
    from core.memory.database import db_manager
    from core.memory.models import Base
    from core.mission.worker_registry import WorkerRegistry

    settings = Settings.load_settings()
    db_file = f"test_worker_reg_{uuid4().hex}.db"
    db_manager.init(settings, connection_url=f"sqlite+aiosqlite:///{db_file}")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.run_sync(Base.metadata.create_all)

    registry = WorkerRegistry(db_manager=db_manager)

    yield {
        "registry": registry,
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


# ===========================================================================
# 1. Constructor validation
# ===========================================================================


class TestConstructor:
    def test_requires_db_manager(self) -> None:
        from core.mission.worker_registry import WorkerRegistry

        with pytest.raises(ValueError, match=r"requires db_manager"):
            WorkerRegistry(db_manager=None)

    def test_rejects_non_positive_grace(self) -> None:
        from core.mission.worker_registry import WorkerRegistry

        with pytest.raises(ValueError, match=r"heartbeat_grace_seconds must be > 0"):
            WorkerRegistry(
                db_manager=object(),
                heartbeat_grace_seconds=0,
            )


# ===========================================================================
# 2. Register
# ===========================================================================


class TestRegister:
    async def test_register_creates_row(self, registry_env: Any) -> None:
        worker_id = uuid4()
        snap = await registry_env["registry"].register(
            worker_id=worker_id,
            hostname="host-a",
            pid=4242,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        assert snap.worker_id == worker_id
        assert snap.hostname == "host-a"
        assert snap.pid == 4242
        assert snap.status == "ONLINE"
        assert snap.active_tasks == 0
        assert snap.last_heartbeat is not None

    async def test_register_is_idempotent(self, registry_env: Any) -> None:
        """Re-registering the same ``worker_id`` UPDATEs the row in place
        — no DUPLICATE on PK conflict (per spec §4.4 the worker_id is
        stable across restarts).
        """
        worker_id = uuid4()
        first = await registry_env["registry"].register(
            worker_id=worker_id,
            hostname="host-a",
            pid=1,
            capabilities={"platforms": ["linux"], "skills": []},
        )
        second = await registry_env["registry"].register(
            worker_id=worker_id,
            hostname="host-b",
            pid=2,
            capabilities={"platforms": ["macos"], "skills": ["x"]},
        )
        assert second.worker_id == worker_id
        assert second.hostname == "host-b"
        assert second.pid == 2
        # last_heartbeat preserved on re-register (heartbeat timer owns it)
        assert second.last_heartbeat == first.last_heartbeat
        # started_at preserved on re-register
        assert second.started_at == first.started_at
        # Only one row in the table
        all_workers = await registry_env["registry"].list_all()
        assert len(all_workers) == 1

    async def test_register_rejects_bad_status(self, registry_env: Any) -> None:
        with pytest.raises(ValueError, match=r"status must be one of"):
            await registry_env["registry"].register(
                worker_id=uuid4(),
                hostname="host-a",
                pid=1,
                capabilities={"platforms": [], "skills": []},
                status="BOGUS",
            )

    async def test_register_rejects_non_dict_capabilities(
        self, registry_env: Any
    ) -> None:
        with pytest.raises(ValueError, match=r"capabilities must be a dict"):
            await registry_env["registry"].register(
                worker_id=uuid4(),
                hostname="host-a",
                pid=1,
                capabilities=["not", "a", "dict"],
            )

    async def test_register_rejects_empty_hostname(self, registry_env: Any) -> None:
        with pytest.raises(ValueError, match=r"hostname must be a non-empty str"):
            await registry_env["registry"].register(
                worker_id=uuid4(),
                hostname="",
                pid=1,
                capabilities={"platforms": [], "skills": []},
            )

    async def test_register_rejects_non_positive_pid(self, registry_env: Any) -> None:
        with pytest.raises(ValueError, match=r"pid must be a positive int"):
            await registry_env["registry"].register(
                worker_id=uuid4(),
                hostname="host-a",
                pid=0,
                capabilities={"platforms": [], "skills": []},
            )


# ===========================================================================
# 3. Heartbeat
# ===========================================================================


class TestHeartbeat:
    async def test_heartbeat_bumps_last_heartbeat(self, registry_env: Any) -> None:
        worker_id = uuid4()
        snap = await registry_env["registry"].register(
            worker_id=worker_id,
            hostname="host-a",
            pid=1,
            capabilities={"platforms": [], "skills": []},
        )
        # Force a clock shift by patching the helper's clock to one that
        # is 5 seconds in the future.
        from datetime import datetime as _dt
        from datetime import timezone as _tz

        future_clock = lambda: _dt.now(_tz.utc) + timedelta(seconds=5)  # noqa: E731
        registry_env["registry"]._clock = future_clock
        post_status = await registry_env["registry"].heartbeat(worker_id=worker_id)
        assert post_status == "ONLINE"
        snap2 = await registry_env["registry"].get(worker_id)
        assert snap2 is not None
        assert snap2.last_heartbeat is not None
        # SQLite drops tzinfo on roundtrip; the snapshot normalizes to UTC
        # so a tz-aware comparison is safe.
        assert snap2.last_heartbeat > snap.last_heartbeat.replace(
            tzinfo=(
                snap.last_heartbeat.tzinfo
                if snap.last_heartbeat.tzinfo is not None
                else _tz.utc
            )
        )

    async def test_heartbeat_updates_active_tasks(self, registry_env: Any) -> None:
        worker_id = uuid4()
        await registry_env["registry"].register(
            worker_id=worker_id,
            hostname="host-a",
            pid=1,
            capabilities={"platforms": [], "skills": []},
        )
        await registry_env["registry"].heartbeat(worker_id=worker_id, active_tasks=5)
        snap = await registry_env["registry"].get(worker_id)
        assert snap is not None
        assert snap.active_tasks == 5

    async def test_heartbeat_returns_none_for_unknown_worker(
        self, registry_env: Any
    ) -> None:
        post_status = await registry_env["registry"].heartbeat(worker_id=uuid4())
        assert post_status is None

    async def test_heartbeat_promotes_offline_to_online(
        self, registry_env: Any
    ) -> None:
        """A worker that was marked OFFLINE is re-promoted on heartbeat."""
        worker_id = uuid4()
        await registry_env["registry"].register(
            worker_id=worker_id,
            hostname="host-a",
            pid=1,
            capabilities={"platforms": [], "skills": []},
        )
        await registry_env["registry"].mark_offline(worker_id)
        snap = await registry_env["registry"].get(worker_id)
        assert snap is not None
        assert snap.status == "OFFLINE"
        # Now heartbeat — should auto-promote.
        post_status = await registry_env["registry"].heartbeat(worker_id=worker_id)
        assert post_status == "ONLINE"
        snap2 = await registry_env["registry"].get(worker_id)
        assert snap2 is not None
        assert snap2.status == "ONLINE"

    async def test_heartbeat_rejects_negative_active_tasks(
        self, registry_env: Any
    ) -> None:
        worker_id = uuid4()
        await registry_env["registry"].register(
            worker_id=worker_id,
            hostname="host-a",
            pid=1,
            capabilities={"platforms": [], "skills": []},
        )
        with pytest.raises(ValueError, match=r"active_tasks must be a non-negative"):
            await registry_env["registry"].heartbeat(
                worker_id=worker_id, active_tasks=-1
            )


# ===========================================================================
# 4. mark_offline
# ===========================================================================


class TestMarkOffline:
    async def test_mark_offline_sets_status(self, registry_env: Any) -> None:
        worker_id = uuid4()
        await registry_env["registry"].register(
            worker_id=worker_id,
            hostname="host-a",
            pid=1,
            capabilities={"platforms": [], "skills": []},
        )
        ok = await registry_env["registry"].mark_offline(worker_id)
        assert ok is True
        snap = await registry_env["registry"].get(worker_id)
        assert snap is not None
        assert snap.status == "OFFLINE"

    async def test_mark_offline_returns_false_for_unknown(
        self, registry_env: Any
    ) -> None:
        ok = await registry_env["registry"].mark_offline(uuid4())
        assert ok is False

    async def test_mark_offline_rejects_non_uuid(self, registry_env: Any) -> None:
        with pytest.raises(ValueError, match=r"worker_id must be a UUID"):
            await registry_env["registry"].mark_offline("not-a-uuid")


# ===========================================================================
# 5. list_active (D-1 sweep)
# ===========================================================================


class TestListActive:
    async def test_list_active_returns_online_within_grace(
        self, registry_env: Any
    ) -> None:
        worker_id = uuid4()
        await registry_env["registry"].register(
            worker_id=worker_id,
            hostname="host-a",
            pid=1,
            capabilities={"platforms": [], "skills": []},
        )
        # Default grace is 15s; a freshly registered worker is well within.
        active = await registry_env["registry"].list_active()
        assert any(w.worker_id == worker_id for w in active)

    async def test_list_active_sweeps_stale_to_offline(self, registry_env: Any) -> None:
        """A worker whose ``last_heartbeat`` is past the grace is
        marked OFFLINE and removed from the active list."""
        from core.runtime.mission_models import WorkerRegistryModel

        worker_id = uuid4()
        await registry_env["registry"].register(
            worker_id=worker_id,
            hostname="host-a",
            pid=1,
            capabilities={"platforms": [], "skills": []},
        )
        # Force the heartbeat 30 seconds into the past.
        db = registry_env["db_manager"]
        async with db.session() as session:
            async with session.begin():
                row = await session.get(WorkerRegistryModel, worker_id)
                assert row is not None
                row.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=30)
        # Default grace is 15s — sweep should demote the worker.
        active = await registry_env["registry"].list_active()
        assert all(w.worker_id != worker_id for w in active)
        snap = await registry_env["registry"].get(worker_id)
        assert snap is not None
        assert snap.status == "OFFLINE"

    async def test_list_active_rejects_non_positive_grace(
        self, registry_env: Any
    ) -> None:
        with pytest.raises(ValueError, match=r"grace_seconds must be > 0"):
            await registry_env["registry"].list_active(grace_seconds=0)


# ===========================================================================
# 6. get / list_all
# ===========================================================================


class TestReadHelpers:
    async def test_get_returns_none_for_unknown_worker(self, registry_env: Any) -> None:
        snap = await registry_env["registry"].get(uuid4())
        assert snap is None

    async def test_get_rejects_non_uuid(self, registry_env: Any) -> None:
        with pytest.raises(ValueError, match=r"worker_id must be a UUID"):
            await registry_env["registry"].get("not-a-uuid")

    async def test_list_all_returns_every_row(self, registry_env: Any) -> None:
        a = uuid4()
        b = uuid4()
        await registry_env["registry"].register(
            worker_id=a,
            hostname="host-a",
            pid=1,
            capabilities={"platforms": [], "skills": []},
        )
        await registry_env["registry"].register(
            worker_id=b,
            hostname="host-b",
            pid=2,
            capabilities={"platforms": [], "skills": []},
        )
        await registry_env["registry"].mark_offline(b)
        all_rows = await registry_env["registry"].list_all()
        ids = {w.worker_id for w in all_rows}
        assert a in ids
        assert b in ids
        # And offline status is preserved (list_all does not sweep).
        statuses = {w.worker_id: w.status for w in all_rows}
        assert statuses[a] == "ONLINE"
        assert statuses[b] == "OFFLINE"

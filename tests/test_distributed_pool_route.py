"""
PHASE: 45 (M6.4.A)
STATUS: TEST
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (§6 REST API Contracts — distributed pool)
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md                          (M6.4.A — distributed_pool REST routes)

Tests for ``api.routes.distributed_pool`` (M6.4.A — REST surface).

The route layer is intentionally thin — it depends on
``DistributedRouter`` + ``WorkerRegistry`` through the FastAPI
``get_distributed_router`` dependency, and the heavy lifting (DB,
routing decisions, append-only log) is in ``core/mission/``.

These tests use ``fastapi.testclient.TestClient`` with the
``get_distributed_router`` dependency overridden to point at the
hermetic in-memory SQLite fixture (the same pattern as
``test_mission_lifecycle.py``).

Coverage target: ≥85% on ``api/routes/distributed_pool.py``.

Headline scenarios:
* GET /workers returns every registered worker
* POST /workers/{id}/heartbeat bumps the row + returns status
* POST /workers/{id}/heartbeat on unknown worker returns 404
* POST /tasks/route picks an eligible worker (LOCAL_ONLY)
* POST /tasks/route with REMOTE_PREFERRED returns 501
* POST /tasks/route with no eligible worker returns 404 (default policy)
* GET /routing?wave_run_id=... returns the recorded decision
* POST /routing/{route_id}/complete marks the row complete
"""

from __future__ import annotations

import os
from typing import Any, AsyncGenerator, Dict
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Auth bypass — set the ``active_context`` ContextVar that
# ``require_permissions`` reads.
# ---------------------------------------------------------------------------


def _install_auth_context(app: FastAPI) -> Any:
    """Install a ``RequestContext`` carrying ``platform.admin`` into
    the route's ContextVar so ``require_permissions`` succeeds.

    Returns the context-token so the caller can reset on teardown.
    """
    from core.security.auth_context import RequestContext, active_context

    token = active_context.set(
        RequestContext(
            user_id=uuid4(),
            username="test_user",
            roles=["admin"],
            permissions=["platform.admin"],
            authentication_method="jwt",
        )
    )
    return token


# ---------------------------------------------------------------------------
# Hermetic fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def route_env() -> AsyncGenerator[Dict[str, Any], None]:
    """Hermetic in-memory SQLite + FastAPI app with auth context set."""
    import core.runtime.mission_models  # noqa: F401 — register models
    from api.dependencies import (
        get_distributed_router,
    )
    from api.routes.distributed_pool import router as dp_router
    from core.config import Settings
    from core.memory.database import db_manager
    from core.memory.models import Base
    from core.mission.distributed_router import DistributedRouter
    from core.mission.worker_registry import WorkerRegistry

    settings = Settings.load_settings()
    db_file = f"test_dpool_{uuid4().hex}.db"
    db_manager.init(settings, connection_url=f"sqlite+aiosqlite:///{db_file}")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.run_sync(Base.metadata.create_all)

    registry = WorkerRegistry(db_manager=db_manager)
    router_obj = DistributedRouter(worker_registry=registry)

    app = FastAPI()
    app.include_router(dp_router)
    app.dependency_overrides[get_distributed_router] = lambda: router_obj

    token = _install_auth_context(app)

    yield {
        "app": app,
        "client": TestClient(app),
        "registry": registry,
        "router_obj": router_obj,
        "db_file": db_file,
    }

    from api.dependencies import active_context  # type: ignore

    active_context.reset(token)

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


# ---------------------------------------------------------------------------
# 1. GET /workers
# ---------------------------------------------------------------------------


class TestListWorkers:
    def test_list_workers_empty(self, route_env: Any) -> None:
        r = route_env["client"].get("/api/v1/distributed/workers")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_workers_after_register(self, route_env: Any) -> None:
        wid = uuid4()
        # Register via the registry helper directly so we don't depend on
        # the auth path of the heartbeat endpoint.
        import asyncio

        async def _reg() -> None:
            await route_env["registry"].register(
                worker_id=wid,
                hostname="host-a",
                pid=4242,
                capabilities={"platforms": ["linux"], "skills": []},
            )

        asyncio.get_event_loop().run_until_complete(_reg()) if False else asyncio.run(
            _reg()
        )
        r = route_env["client"].get("/api/v1/distributed/workers")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["worker_id"] == str(wid)
        assert data[0]["hostname"] == "host-a"
        assert data[0]["status"] == "ONLINE"


# ---------------------------------------------------------------------------
# 2. POST /workers/{id}/heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    def test_heartbeat_unknown_worker_returns_404(self, route_env: Any) -> None:
        r = route_env["client"].post(
            f"/api/v1/distributed/workers/{uuid4()}/heartbeat",
            json={"active_tasks": 1},
        )
        assert r.status_code == 404

    def test_heartbeat_known_worker_returns_status(self, route_env: Any) -> None:
        import asyncio

        wid = uuid4()

        async def _reg() -> None:
            await route_env["registry"].register(
                worker_id=wid,
                hostname="host-a",
                pid=1,
                capabilities={"platforms": ["linux"], "skills": []},
            )

        asyncio.run(_reg())
        r = route_env["client"].post(
            f"/api/v1/distributed/workers/{wid}/heartbeat",
            json={"active_tasks": 2},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["worker_id"] == str(wid)
        assert body["status"] == "ONLINE"

    def test_heartbeat_rejects_negative_active_tasks(self, route_env: Any) -> None:
        wid = uuid4()
        r = route_env["client"].post(
            f"/api/v1/distributed/workers/{wid}/heartbeat",
            json={"active_tasks": -1},
        )
        # Pydantic validation rejects negative -> 422.
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# 3. POST /tasks/route
# ---------------------------------------------------------------------------


class TestRouteTask:
    def test_route_with_no_workers_returns_404(self, route_env: Any) -> None:
        r = route_env["client"].post(
            "/api/v1/distributed/tasks/route",
            json={
                "wave_run_id": str(uuid4()),
                "required_platform": "linux",
            },
        )
        assert r.status_code == 404

    def test_route_with_eligible_worker_returns_200(self, route_env: Any) -> None:
        import asyncio

        wid = uuid4()

        async def _reg() -> None:
            await route_env["registry"].register(
                worker_id=wid,
                hostname="host-a",
                pid=1,
                capabilities={"platforms": ["linux"], "skills": []},
            )

        asyncio.run(_reg())
        r = route_env["client"].post(
            "/api/v1/distributed/tasks/route",
            json={
                "wave_run_id": str(uuid4()),
                "required_platform": "linux",
                "policy": "ANY",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["worker"]["worker_id"] == str(wid)
        assert body["decision_reason"] == "ROUTED_LOCAL"

    def test_route_remote_preferred_returns_501(self, route_env: Any) -> None:
        import asyncio

        wid = uuid4()

        async def _reg() -> None:
            await route_env["registry"].register(
                worker_id=wid,
                hostname="host-a",
                pid=1,
                capabilities={"platforms": ["linux"], "skills": []},
            )

        asyncio.run(_reg())
        r = route_env["client"].post(
            "/api/v1/distributed/tasks/route",
            json={
                "wave_run_id": str(uuid4()),
                "policy": "REMOTE_PREFERRED",
            },
        )
        assert r.status_code == 501

    def test_route_invalid_policy_returns_422(self, route_env: Any) -> None:
        r = route_env["client"].post(
            "/api/v1/distributed/tasks/route",
            json={
                "wave_run_id": str(uuid4()),
                "policy": "BOGUS",
            },
        )
        assert r.status_code == 422

    def test_route_allow_no_worker_returns_200_with_null_worker(
        self, route_env: Any
    ) -> None:
        r = route_env["client"].post(
            "/api/v1/distributed/tasks/route",
            json={
                "wave_run_id": str(uuid4()),
                "required_platform": "linux",
                "allow_no_worker": True,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["worker"] is None
        assert body["decision_reason"] == "NO_ELIGIBLE_WORKER"


# ---------------------------------------------------------------------------
# 4. GET /routing + POST /routing/{route_id}/complete
# ---------------------------------------------------------------------------


class TestRoutingAudit:
    def test_get_routing_for_wave_returns_recorded_decisions(
        self, route_env: Any
    ) -> None:
        import asyncio

        wid = uuid4()
        wave = uuid4()

        async def _reg_and_route() -> str:
            await route_env["registry"].register(
                worker_id=wid,
                hostname="host-a",
                pid=1,
                capabilities={"platforms": ["linux"], "skills": []},
            )
            decision = await route_env["router_obj"].route(
                wave_run_id=wave,
                required_platform="linux",
            )
            return str(decision.route_id)

        rid = asyncio.run(_reg_and_route())
        r = route_env["client"].get(f"/api/v1/distributed/routing?wave_run_id={wave}")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["route_id"] == rid

    def test_complete_routing_marks_completed(self, route_env: Any) -> None:
        import asyncio

        wid = uuid4()
        wave = uuid4()

        async def _reg_and_route() -> str:
            await route_env["registry"].register(
                worker_id=wid,
                hostname="host-a",
                pid=1,
                capabilities={"platforms": ["linux"], "skills": []},
            )
            decision = await route_env["router_obj"].route(
                wave_run_id=wave,
                required_platform="linux",
            )
            return str(decision.route_id)

        rid = asyncio.run(_reg_and_route())
        r = route_env["client"].post(
            f"/api/v1/distributed/routing/{rid}/complete",
            json={},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["completed"] is True

    def test_complete_unknown_route_id_returns_false(self, route_env: Any) -> None:
        r = route_env["client"].post(
            f"/api/v1/distributed/routing/{uuid4()}/complete",
            json={},
        )
        assert r.status_code == 200
        assert r.json()["completed"] is False

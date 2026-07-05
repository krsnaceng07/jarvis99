"""JARVIS OS - Missions REST API Gateway Integration Tests."""

from typing import Any, AsyncGenerator, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import set_kernel
from api.routes import missions
from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.kernel import Kernel
from core.memory.database import db_manager
from core.memory.models import Base
from core.runtime.mission import MissionManager
from tests.test_platform_health import authenticated_context


@pytest.fixture
async def setup_api_env() -> AsyncGenerator[Dict[str, Any], None]:
    """Setup app context, mock kernel, and FastAPI TestClient."""
    import os
    from uuid import uuid4

    settings = Settings.load_settings()

    # Import models
    import core.runtime.mission_models  # noqa: F401

    db_file = f"test_missions_{uuid4().hex}.db"
    db_manager.init(settings, connection_url=f"sqlite+aiosqlite:///{db_file}")

    from sqlalchemy import text

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.run_sync(Base.metadata.create_all)

    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    mission_mgr = MissionManager(
        settings=settings,
        db_manager=db_manager,
        event_bus=event_bus,
        vault_manager=None,
        orchestrator=None,
    )
    await mission_mgr.initialize()
    await mission_mgr.start()

    kernel = Kernel()
    kernel.container.register_singleton(Settings, settings)
    kernel.container.register_singleton(MissionManager, mission_mgr)
    set_kernel(kernel)

    from api.middleware import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(missions.router)
    client = TestClient(app)

    yield {
        "mission_mgr": mission_mgr,
        "client": client,
    }

    await mission_mgr.stop()
    await mission_mgr.shutdown()
    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()

    for suffix in ("", "-wal", "-shm", "-journal"):
        path = db_file + suffix
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


@pytest.mark.asyncio
async def test_missions_api_lifecycle(setup_api_env: Dict[str, Any]) -> None:
    """Verify HTTP API endpoints for creating, listing, pausing, and resuming missions."""
    client = setup_api_env["client"]

    # 1. Create Mission (auth check first)
    response = client.post(
        "/api/v1/missions",
        json={"goal": "Deploy backend service", "budget_limit": 50.00},
    )
    assert response.status_code == 401  # Requires authenticated context

    with authenticated_context():
        # Create
        response = client.post(
            "/api/v1/missions",
            json={"goal": "Deploy backend service", "budget_limit": 50.00},
        )
        assert response.status_code == 201
        data = response.json()
        mission_id = data["mission_id"]
        assert data["goal"] == "Deploy backend service"
        assert data["budget_limit"] == 50.00

        # List
        list_res = client.get("/api/v1/missions")
        assert list_res.status_code == 200
        assert len(list_res.json()) == 1
        assert list_res.json()[0]["mission_id"] == mission_id

        # Get detail
        detail_res = client.get(f"/api/v1/missions/{mission_id}")
        assert detail_res.status_code == 200
        assert detail_res.json()["goal"] == "Deploy backend service"

        # Pause
        pause_res = client.post(f"/api/v1/missions/{mission_id}/pause")
        assert pause_res.status_code == 200
        assert pause_res.json()["status"] == "PAUSED"

        # Resume
        resume_res = client.post(f"/api/v1/missions/{mission_id}/resume")
        assert resume_res.status_code == 200
        assert resume_res.json()["status"] == "RUNNING"

        # Cancel
        cancel_res = client.post(f"/api/v1/missions/{mission_id}/cancel")
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "CANCELLED"

        # Timeline
        timeline_res = client.get(f"/api/v1/missions/{mission_id}/timeline")
        assert timeline_res.status_code == 200
        assert len(timeline_res.json()) > 0

        # Checkpoints
        cp_res = client.get(f"/api/v1/missions/{mission_id}/checkpoints")
        assert cp_res.status_code == 200

"""JARVIS OS - Preflight Checker Unit & Integration Tests.

Validates the preflight validator constraints against system dependencies.
"""

import contextlib
import shutil
from typing import Any, AsyncGenerator, Dict, Generator, List
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import set_kernel
from api.routes import platform
from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.kernel import Kernel
from core.memory.database import db_manager
from core.memory.models import Base
from core.runtime.deployment import DeploymentHealthManager
from core.security.auth_context import RequestContext, active_context


class MockVaultManager:
    def __init__(self, locked: bool = False) -> None:
        self._locked = locked

    def is_locked(self) -> bool:
        return self._locked


@contextlib.contextmanager
def authenticated_context(
    permissions: List[str] | None = None,
) -> Generator[None, None, None]:
    """Helper to mock security credentials on active ContextVar."""
    token = active_context.set(
        RequestContext(
            user_id=uuid4(),
            username="admin_user",
            roles=["admin"],
            permissions=permissions if permissions is not None else ["platform.admin"],
            authentication_method="jwt",
        )
    )
    try:
        yield
    finally:
        active_context.reset(token)


@pytest.fixture
async def setup_preflight_env() -> AsyncGenerator[Dict[str, Any], None]:
    """Initialize test environment for preflight checks."""
    import api.dependencies

    api.dependencies._kernel = None

    settings = Settings.load_settings()

    import core.memory.security_models  # noqa: F401
    import core.observability.models  # noqa: F401
    import core.runtime.persistence_models  # noqa: F401
    import core.tools.execution_models  # noqa: F401

    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    event_bus = MemoryEventBus()

    await event_bus.initialize()
    await event_bus.start()

    vault_mgr = MockVaultManager(locked=False)
    orch = None
    admin_mgr = None

    health_mgr = DeploymentHealthManager(
        settings=settings,
        db_manager=db_manager,
        event_bus=event_bus,
        vault_manager=vault_mgr,
        orchestrator=orch,
        admin_manager=admin_mgr,
    )
    await health_mgr.initialize()
    await health_mgr.start()

    kernel = Kernel()
    kernel.container.register_singleton(Settings, settings)
    kernel.container.register_singleton(DeploymentHealthManager, health_mgr)
    set_kernel(kernel)

    from api.middleware import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(platform.router)
    client = TestClient(app)

    yield {
        "health_mgr": health_mgr,
        "client": client,
        "vault": vault_mgr,
        "event_bus": event_bus,
    }

    await health_mgr.stop()
    await health_mgr.shutdown()
    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()


@pytest.mark.asyncio
async def test_preflight_passed_under_normal_conditions(
    setup_preflight_env: Dict[str, Any],
) -> None:
    """Verify preflight check passes when dependencies are functioning normally."""
    client = setup_preflight_env["client"]
    with authenticated_context():
        response = client.post("/api/v1/platform/preflight")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PASSED"
        assert data["checks"]["database"] == "OK"
        assert data["checks"]["vault"] == "UNLOCKED"
        assert data["checks"]["disk"] == "OK"


@pytest.mark.asyncio
async def test_preflight_disk_limit_exceeded(
    setup_preflight_env: Dict[str, Any], monkeypatch: Any
) -> None:
    """Verify preflight checker flags disk limit errors when usage threshold is breached."""
    client = setup_preflight_env["client"]

    # Mock shutil.disk_usage to return 98% space used
    def mock_disk_usage(path: str) -> Any:
        return (100, 98, 2)  # total=100, used=98, free=2

    monkeypatch.setattr(shutil, "disk_usage", mock_disk_usage)
    with authenticated_context():
        response = client.post("/api/v1/platform/preflight")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "FAILED"
        assert "LIMIT_EXCEEDED" in data["checks"]["disk"]

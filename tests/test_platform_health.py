"""JARVIS OS - Platform Health and Operational State Tests.

Validates status, liveness, and readiness API routes under normal and degraded system conditions.
"""

import contextlib
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
async def setup_platform_env() -> AsyncGenerator[Dict[str, Any], None]:
    """Initialize test environment for platform readiness and liveness checks."""
    import api.dependencies

    api.dependencies._kernel = None

    settings = Settings.load_settings()

    import core.memory.security_models  # noqa: F401
    import core.observability.models  # noqa: F401
    import core.runtime.persistence_models  # noqa: F401
    import core.tools.execution_models  # noqa: F401

    # Initialize SQLite memory database
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

    # Build a mock kernel for FastAPI dependency injection
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

    # Cleanup
    await health_mgr.stop()
    await health_mgr.shutdown()
    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()


@pytest.mark.asyncio
async def test_liveness_endpoint(setup_platform_env: Dict[str, Any]) -> None:
    """Verify liveness probe returns alive status and requires no deep health status checks."""
    client = setup_platform_env["client"]
    with authenticated_context():
        response = client.get("/api/v1/platform/liveness")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_status_endpoint(setup_platform_env: Dict[str, Any]) -> None:
    """Verify status endpoint returns healthy with the active environment settings."""
    client = setup_platform_env["client"]
    with authenticated_context():
        response = client.get("/api/v1/platform/status")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert "environment" in response.json()


@pytest.mark.asyncio
async def test_readiness_endpoint_healthy(setup_platform_env: Dict[str, Any]) -> None:
    """Verify readiness check passes when dependencies are available."""
    client = setup_platform_env["client"]
    with authenticated_context():
        response = client.get("/api/v1/platform/readiness")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "CONNECTED"
        assert data["vault"] == "UNLOCKED"


@pytest.mark.asyncio
async def test_readiness_endpoint_unauthorized(
    setup_platform_env: Dict[str, Any],
) -> None:
    """Verify access requires platform.admin permission scope."""
    client = setup_platform_env["client"]
    with authenticated_context(permissions=[]):
        response = client.get("/api/v1/platform/readiness")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_readiness_endpoint_degraded(
    setup_platform_env: Dict[str, Any], monkeypatch: Any
) -> None:
    """Verify readiness check fails with HTTP 503 if system vault is locked or database is disconnected."""
    client = setup_platform_env["client"]
    setup_platform_env["health_mgr"]

    # 1. Lock vault
    setup_platform_env["vault"]._locked = True
    with authenticated_context():
        response = client.get("/api/v1/platform/readiness")
        assert response.status_code == 503
        assert response.json()["detail"]["status"] == "not_ready"
        assert response.json()["detail"]["vault"] == "LOCKED"

    # Unlock vault
    setup_platform_env["vault"]._locked = False

    # 2. Database connection failure simulation
    @contextlib.asynccontextmanager
    async def mock_session_fail(*args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
        raise Exception("DB Down")
        yield

    monkeypatch.setattr(db_manager, "session", mock_session_fail)
    with authenticated_context():
        response = client.get("/api/v1/platform/readiness")
        assert response.status_code == 503
        assert response.json()["detail"]["database"] == "DISCONNECTED"

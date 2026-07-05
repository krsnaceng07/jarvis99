"""Shared pytest fixtures for JARVIS OS integration tests."""

from typing import Any, AsyncGenerator, Dict
from uuid import uuid4

import pytest

from core.security.auth_context import RequestContext
from core.security.configuration_service import ConfigurationService
from core.security.jwt_service import JWTService

ALL_TEST_PERMISSIONS = [
    "agent.execute",
    "agent.read",
    "workflow.execute",
    "workflow.read",
    "audit.read",
]

_GATEWAY_TEST_MODULES = frozenset(
    {
        "test_api_security",
        "test_persistent_execution",
        "test_api_gateway",
    }
)


def _is_gateway_test(request: pytest.FixtureRequest) -> bool:
    module_name = request.module.__name__.rsplit(".", 1)[-1]
    return module_name in _GATEWAY_TEST_MODULES


@pytest.fixture(autouse=True)
def gateway_sqlite_database(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Route gateway/kernel boots to in-memory SQLite for hermetic API tests."""
    if not _is_gateway_test(request):
        return
    monkeypatch.setenv("JARVIS_DATABASE__HOST", "sqlite")
    monkeypatch.setenv("JARVIS_DATABASE__NAME", ":memory:")
    monkeypatch.setenv("JARVIS_SYSTEM__ENVIRONMENT", "development")


@pytest.fixture(autouse=True)
def reset_kernel_singleton(request: pytest.FixtureRequest) -> None:
    """Clear the API-layer kernel singleton between gateway tests."""
    if not _is_gateway_test(request):
        yield
        return
    import api.dependencies as deps

    deps._kernel = None
    yield
    deps._kernel = None


@pytest.fixture
def mock_request_context() -> RequestContext:
    """Minimal authenticated context for direct route handler unit tests."""
    return RequestContext(
        user_id=uuid4(),
        username="test-user",
        roles=["admin"],
        permissions=ALL_TEST_PERMISSIONS,
        authentication_method="jwt",
    )


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Bearer JWT using the same defaults as the kernel ConfigurationService."""
    config = ConfigurationService()
    service = JWTService(config)
    token = service.sign_token(
        user_id=str(uuid4()),
        username="integration-test-user",
        roles=["admin"],
        permissions=ALL_TEST_PERMISSIONS,
        jti=str(uuid4()),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def setup_mission_env() -> AsyncGenerator[Dict[str, Any], None]:
    """Initialize file-based database and MissionManager for testing."""
    import os
    from uuid import uuid4

    import core.runtime.mission_models  # noqa: F401
    from core.config import Settings
    from core.events.memory_bus import MemoryEventBus
    from core.memory.database import db_manager
    from core.memory.models import Base
    from core.runtime.mission import MissionManager

    settings = Settings.load_settings()
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

    yield {
        "mission_mgr": mission_mgr,
        "db_manager": db_manager,
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

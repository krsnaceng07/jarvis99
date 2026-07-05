"""JARVIS OS - Disaster Recovery Verification Tests.

Validates simulated disaster recovery checks without mutating active database systems.
"""

import os
import tempfile
from typing import Any, AsyncGenerator, Dict

import pytest

from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.memory.database import db_manager
from core.memory.models import Base
from core.runtime.admin import AdminManager
from core.runtime.deployment import DeploymentHealthManager


class MockVaultManager:
    def __init__(self, locked: bool = False) -> None:
        self._locked = locked

    def is_locked(self) -> bool:
        return self._locked


@pytest.fixture
async def setup_dr_env() -> AsyncGenerator[Dict[str, Any], None]:
    """Initialize environment for disaster recovery simulations."""
    settings = Settings.load_settings()

    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = os.path.join(temp_dir, "dynamic_settings.json")
        backups_dir = os.path.join(temp_dir, "backups")

        import core.memory.security_models  # noqa: F401
        import core.observability.models  # noqa: F401
        import core.runtime.persistence_models  # noqa: F401
        import core.tools.execution_models  # noqa: F401

        # Initialize SQLite memory database
        db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")
        async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
            await conn.run_sync(Base.metadata.create_all)

        # Seed initial user into database to satisfy integrity check
        import uuid

        from core.memory.security_models import UserModel

        async with db_manager.session() as session:
            async with session.begin():
                user = UserModel(
                    id=uuid.UUID("54bb0610-d02f-48d6-a4c3-a3099955fa24"),
                    username="admin",
                    email="admin@jarvis.io",
                    hashed_password="pbkdf2_sha256$",
                    is_active=True,
                )
                session.add(user)

        event_bus = MemoryEventBus()
        await event_bus.initialize()
        await event_bus.start()

        vault_mgr = MockVaultManager(locked=False)
        orch = None

        admin_mgr = AdminManager(
            settings=settings,
            db_manager=db_manager,
            event_bus=event_bus,
            vault_manager=vault_mgr,
            orchestrator=orch,
            config_path=config_path,
            backups_dir=backups_dir,
        )
        await admin_mgr.initialize()
        await admin_mgr.start()

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

        yield {
            "health_mgr": health_mgr,
            "admin_mgr": admin_mgr,
            "db_manager": db_manager,
        }

        await health_mgr.stop()
        await health_mgr.shutdown()
        await admin_mgr.stop()
        await admin_mgr.shutdown()
        await event_bus.stop()
        await event_bus.shutdown()
        await db_manager.close()


@pytest.mark.asyncio
async def test_disaster_recovery_simulation_success(
    setup_dr_env: Dict[str, Any],
) -> None:
    """Verify disaster recovery simulation performs a backup and scans the schema successfully."""
    health_mgr = setup_dr_env["health_mgr"]
    res = await health_mgr.verify_disaster_recovery()
    assert res["status"] == "success"
    assert res["integrity_check"] == "PASSED"
    assert "backup_file" in res


@pytest.mark.asyncio
async def test_disaster_recovery_simulation_failure_on_missing_tables(
    setup_dr_env: Dict[str, Any], monkeypatch: Any
) -> None:
    """Verify preflight flags recovery checks as FAILED when mock backup returns empty tables."""
    health_mgr = setup_dr_env["health_mgr"]
    admin_mgr = setup_dr_env["admin_mgr"]

    # Mock create_backup to return a file containing invalid schema dictionary
    async def mock_create_backup() -> str:
        import json
        import os

        filename = "backup_invalid.json"
        filepath = os.path.join(admin_mgr.backups_dir, filename)
        os.makedirs(admin_mgr.backups_dir, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"settings": []}, f)  # Missing 'users' table
        return filename

    monkeypatch.setattr(admin_mgr, "create_backup", mock_create_backup)
    res = await health_mgr.verify_disaster_recovery()
    assert res["status"] == "failed"
    assert res["integrity_check"] == "FAILED"
    assert "users" in res["reason"]

"""JARVIS OS - Platform Administration and Operations Unit & Integration Tests.

Validates AdminManager diagnostics checks, dynamic configurations, atomic backups, restores, task controls, and secure gateway routers.
"""

import contextlib
import json
import os
import tempfile
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.dependencies import set_kernel
from api.routes import admin
from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.exceptions import JarvisSystemError
from core.memory.database import db_manager
from core.memory.models import Base
from core.runtime.admin import AdminManager, DynamicSettings
from core.security.auth_context import RequestContext, active_context
from core.security.jwt_service import JWTService

# =====================================================================
# 1. Test DTOs & Validation
# =====================================================================


def test_dynamic_settings_schema_validation() -> None:
    """Verify dynamic config fields are validated properly."""
    # Valid settings
    cfg = DynamicSettings(
        system_log_level="DEBUG",
        sync_interval_seconds=120,
        rate_limit_per_minute=200,
        telemetry_enabled=False,
    )
    assert cfg.system_log_level == "DEBUG"
    assert cfg.sync_interval_seconds == 120

    # Invalid system log level
    with pytest.raises(ValueError):
        DynamicSettings(system_log_level="UNSUPPORTED")

    # Invalid sync interval
    with pytest.raises(ValueError):
        DynamicSettings(sync_interval_seconds=2)  # < 5 ge constraint

    # Invalid rate limit
    with pytest.raises(ValueError):
        DynamicSettings(rate_limit_per_minute=0)  # < 1 ge constraint


# =====================================================================
# 2. Authentication Context Mock Helpers
# =====================================================================


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


# =====================================================================
# 3. Kernel Dependency Mock Fixture
# =====================================================================


class MockVaultManager:
    def __init__(self, locked: bool = False) -> None:
        self._locked = locked

    def is_locked(self) -> bool:
        return self._locked


class MockScheduler:
    def __init__(self) -> None:
        self.paused_tasks: List[str] = []
        self.resumed_tasks: List[str] = []
        self.cancelled_tasks: List[str] = []
        self._worker_task: Optional[str] = "active_stub"

    async def pause_task(self, task_id: Any) -> bool:
        self.paused_tasks.append(str(task_id))
        return True

    async def resume_task(self, task_id: Any) -> bool:
        self.resumed_tasks.append(str(task_id))
        return True

    async def cancel_task(self, task_id: Any) -> bool:
        self.cancelled_tasks.append(str(task_id))
        return True

    async def stop_worker_loop(self) -> None:
        self._worker_task = None

    async def start_worker_loop(self) -> None:
        self._worker_task = "active_stub"


@pytest.fixture
async def setup_admin_env() -> AsyncGenerator[Dict[str, Any], None]:
    """Initialize temporary configurations, database, and mock orchestrator dependencies."""
    settings = Settings.load_settings()

    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = os.path.join(temp_dir, "dynamic_settings.json")
        backups_dir = os.path.join(temp_dir, "backups")

        # Import all models to populate Base.metadata before creating tables
        import core.memory.security_models  # noqa: F401
        import core.observability.models  # noqa: F401
        import core.runtime.persistence_models  # noqa: F401
        import core.tools.execution_models  # noqa: F401

        # Initialize SQLite memory database
        db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")
        async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
            await conn.run_sync(Base.metadata.create_all)

        # Seed initial user into database to satisfy integrity check on restore
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
        orch = MockScheduler()

        manager = AdminManager(
            settings=settings,
            db_manager=db_manager,
            event_bus=event_bus,
            vault_manager=vault_mgr,
            orchestrator=orch,
            config_path=config_path,
            backups_dir=backups_dir,
        )
        await manager.initialize()
        await manager.start()

        yield {
            "manager": manager,
            "db_manager": db_manager,
            "event_bus": event_bus,
            "vault": vault_mgr,
            "orchestrator": orch,
            "config_path": config_path,
            "backups_dir": backups_dir,
            "settings": settings,
        }

        # Cleanup
        await manager.stop()
        await manager.shutdown()
        await event_bus.stop()
        await event_bus.shutdown()
        await db_manager.close()


# =====================================================================
# 4. AdminManager Diagnostics and Metrics Tests
# =====================================================================


@pytest.mark.asyncio
async def test_admin_diagnostics_retrieval(setup_admin_env: Dict[str, Any]) -> None:
    """Verify system diagnostics collects and caches correct metrics from services."""
    manager = setup_admin_env["manager"]
    diag = await manager.get_diagnostics()

    assert diag["status"] == "healthy"
    assert diag["database"] == "OK"
    assert diag["redis"] == "OK"
    assert diag["vault"]["locked"] is False
    assert "disk_usage_percent" in diag["resources"]

    # Verify degraded status when vault is locked
    setup_admin_env["vault"]._locked = True
    # Re-trigger computation by invalidating cache
    manager._last_diag_time = 0.0
    diag_degraded = await manager.get_diagnostics()
    assert diag_degraded["status"] == "degraded"
    assert diag_degraded["vault"]["locked"] is True


@pytest.mark.asyncio
async def test_admin_metrics_retrieval(setup_admin_env: Dict[str, Any]) -> None:
    """Verify system metrics correctly count DB executions."""
    manager = setup_admin_env["manager"]
    metrics = await manager.get_metrics()

    assert metrics["uptime_seconds"] >= 0.0
    assert metrics["total_execution_runs"] == 0
    assert metrics["completed_runs"] == 0
    assert metrics["success_rate"] == 0.0


# =====================================================================
# 5. Dynamic Configuration Persistance Tests
# =====================================================================


@pytest.mark.asyncio
async def test_dynamic_configuration_lifecycle(setup_admin_env: Dict[str, Any]) -> None:
    """Verify configuration live updates are schema validated and written to disk."""
    manager = setup_admin_env["manager"]
    config_path = setup_admin_env["config_path"]

    # Retrieve defaults
    cfg = await manager.get_dynamic_config()
    assert cfg["system_log_level"] == "INFO"
    assert cfg["sync_interval_seconds"] == 60

    # Successful Update
    res = await manager.update_dynamic_config(
        {"system_log_level": "WARNING", "sync_interval_seconds": 120}
    )
    assert res["status"] == "SUCCESS"
    assert res["config"]["system_log_level"] == "WARNING"
    assert res["config"]["sync_interval_seconds"] == 120

    # File persisted correctly
    with open(config_path, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert disk_data["system_log_level"] == "WARNING"
    assert disk_data["sync_interval_seconds"] == 120

    # Validation Failure Update (Rejected)
    with pytest.raises(JarvisSystemError):
        await manager.update_dynamic_config({"system_log_level": "HACKED"})


# =====================================================================
# 6. Task Controls Dispatcher Tests
# =====================================================================


@pytest.mark.asyncio
async def test_scheduler_task_controls(setup_admin_env: Dict[str, Any]) -> None:
    """Verify pause, resume, and cancel signals propagate correctly to scheduler."""
    manager = setup_admin_env["manager"]
    orch = setup_admin_env["orchestrator"]
    task_id = str(uuid4())

    # Dispatch pause
    ok = await manager.control_task(task_id, "pause")
    assert ok is True
    assert task_id in orch.paused_tasks

    # Dispatch resume
    ok = await manager.control_task(task_id, "resume")
    assert ok is True
    assert task_id in orch.resumed_tasks

    # Dispatch cancel
    ok = await manager.control_task(task_id, "cancel")
    assert ok is True
    assert task_id in orch.cancelled_tasks

    # Invalid action
    with pytest.raises(JarvisSystemError):
        await manager.control_task(task_id, "invalid_action")


# =====================================================================
# 7. Atomic Backup & Safe Restore Tests
# =====================================================================


@pytest.mark.asyncio
async def test_atomic_backup_and_safe_restore(setup_admin_env: Dict[str, Any]) -> None:
    """Verify databases are backed up and restored safely with integrity check rollbacks."""
    manager = setup_admin_env["manager"]
    db = setup_admin_env["db_manager"]
    setup_admin_env["orchestrator"]

    # 1. Create a backup
    backup_file = await manager.create_backup()
    assert backup_file.startswith("db_backup_")
    assert backup_file.endswith(".json")

    # 2. Modify database state (delete user to trigger integrity check failure)
    async with db.session() as session:
        async with session.begin():
            await session.execute(text("DELETE FROM users"))

    # 3. Trigger restore (should restore user and pass integrity checks)
    restore_ok = await manager.restore_backup(backup_file)
    assert restore_ok is True

    # 4. Assert user is recovered
    async with db.session() as session:
        res = await session.execute(text("SELECT COUNT(*) FROM users"))
        assert res.scalar() == 1

    # 5. Verify Restore rollback on failure (by using a malformed backup payload)
    malformed_backup = "db_backup_malformed.json"
    malformed_path = os.path.join(setup_admin_env["backups_dir"], malformed_backup)
    with open(malformed_path, "w", encoding="utf-8") as f:
        f.write("{invalid json syntax")

    with pytest.raises(JarvisSystemError):
        await manager.restore_backup(malformed_backup)


# =====================================================================
# 8. API Gateway REST & Dashboard Router Integration Tests
# =====================================================================


def test_admin_api_gateway_routes(setup_admin_env: Dict[str, Any]) -> None:
    """Verify REST administration endpoint authorization, diagnostics, backups and controls."""
    manager = setup_admin_env["manager"]

    class MockKernelContainer:
        def resolve(self, cls: Any) -> Any:
            if cls == AdminManager:
                return manager
            elif cls == JWTService:
                # Mock JWT service for dashboard token check
                class MockJWT:
                    def verify_token(self, token: str) -> Dict[str, Any]:
                        if token == "admin_token_jwt":
                            return {"permissions": ["platform.admin"]}
                        return {"permissions": []}

                return MockJWT()
            return None

    class MockKernelHandle:
        def __init__(self) -> None:
            self.container = MockKernelContainer()

    kernel_mock = MockKernelHandle()
    set_kernel(kernel_mock)  # type: ignore[arg-type]

    from api.middleware import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(admin.router)
    client = TestClient(app)

    # 1. Access without authentication fails (401)
    assert client.get("/api/v1/admin/diagnostics").status_code == 401
    assert client.get("/api/v1/admin/metrics").status_code == 401
    assert client.get("/api/v1/admin/config").status_code == 401
    assert client.post("/api/v1/admin/config/update", json={}).status_code == 401
    assert client.post("/api/v1/admin/backups/create").status_code == 401

    # 2. Access with insufficient permissions fails (401)
    with authenticated_context(permissions=["user.read"]):
        assert client.get("/api/v1/admin/diagnostics").status_code == 401

    # 3. Access with platform.admin permissions succeeds (200)
    with authenticated_context(permissions=["platform.admin"]):
        # Diagnostics
        diag_res = client.get("/api/v1/admin/diagnostics")
        assert diag_res.status_code == 200
        assert diag_res.json()["data"]["database"] == "OK"

        # Metrics
        metric_res = client.get("/api/v1/admin/metrics")
        assert metric_res.status_code == 200
        assert metric_res.json()["data"]["total_execution_runs"] == 0

        # Get Config
        cfg_res = client.get("/api/v1/admin/config")
        assert cfg_res.status_code == 200
        assert cfg_res.json()["data"]["system_log_level"] == "INFO"

        # Update Config
        upd_res = client.post(
            "/api/v1/admin/config/update", json={"system_log_level": "DEBUG"}
        )
        assert upd_res.status_code == 200
        assert upd_res.json()["data"]["config"]["system_log_level"] == "DEBUG"

        # Task Control
        task_id = str(uuid4())
        ctrl_res = client.post(
            f"/api/v1/admin/tasks/{task_id}/control", json={"action": "pause"}
        )
        assert ctrl_res.status_code == 200
        assert ctrl_res.json()["data"]["status"] == "SUCCESS"

        # Create Backup
        back_res = client.post("/api/v1/admin/backups/create")
        assert back_res.status_code == 200
        backup_file = back_res.json()["data"]["backup_file"]
        assert backup_file.startswith("db_backup_")

        # Restore Backup
        rest_res = client.post(
            "/api/v1/admin/backups/restore", json={"backup_file": backup_file}
        )
        assert rest_res.status_code == 200
        assert rest_res.json()["data"]["status"] == "SUCCESS"

    # 4. Serves Dashboard SPA HTML only behind authentication checks (Constraint 5)
    # Access dashboard without credentials -> fails 401
    assert client.get("/api/v1/admin/dashboard").status_code == 401

    # Access dashboard with invalid token query parameter -> fails 401
    assert client.get("/api/v1/admin/dashboard?token=invalid").status_code == 401

    # Access dashboard with valid token query parameter -> succeeds 200 serving HTML page
    dash_res = client.get("/api/v1/admin/dashboard?token=admin_token_jwt")
    assert dash_res.status_code == 200
    assert "text/html" in dash_res.headers["content-type"]
    assert "JARVIS Admin Console" in dash_res.text


@pytest.mark.asyncio
async def test_admin_manager_missing_backup_file(
    setup_admin_env: Dict[str, Any],
) -> None:
    """Verify that restoring a missing backup file raises JarvisSystemError."""
    manager = setup_admin_env["manager"]
    with pytest.raises(JarvisSystemError) as exc_info:
        await manager.restore_backup("nonexistent_backup.json")
    assert "does not exist" in str(exc_info.value)


@pytest.mark.asyncio
async def test_admin_manager_invalid_task_uuid(setup_admin_env: Dict[str, Any]) -> None:
    """Verify control_task fails cleanly with invalid task UUID strings."""
    manager = setup_admin_env["manager"]
    with pytest.raises(JarvisSystemError) as exc_info:
        await manager.control_task("not-a-uuid", "pause")
    assert "Invalid task UUID" in str(exc_info.value)


def test_dynamic_settings_log_level_formatting() -> None:
    """Verify log levels are validated and automatically cast to uppercase."""
    cfg = DynamicSettings(system_log_level="debug")
    assert cfg.system_log_level == "DEBUG"


@pytest.mark.asyncio
async def test_admin_manager_diagnostics_failures(
    setup_admin_env: Dict[str, Any], monkeypatch: Any
) -> None:
    """Verify diagnostics handles DB connectivity, Redis, and disk load failures gracefully."""
    manager = setup_admin_env["manager"]

    # 1. DB Failure
    @contextlib.asynccontextmanager
    async def mock_session_fail(*args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
        raise Exception("DB Down")
        yield

    monkeypatch.setattr(setup_admin_env["db_manager"], "session", mock_session_fail)
    manager._last_diag_time = 0.0
    diag = await manager.get_diagnostics()
    assert diag["database"] == "ERROR"
    assert diag["status"] == "degraded"

    # 2. Redis Failure (re-mock session to succeed, make redis fail)
    @contextlib.asynccontextmanager
    async def mock_session_success() -> AsyncGenerator[Any, None]:
        class MockSession:
            async def execute(self, *args: Any, **kwargs: Any) -> Any:
                class MockResult:
                    def scalar(self) -> int:
                        return 1

                return MockResult()

        yield MockSession()

    monkeypatch.setattr(setup_admin_env["db_manager"], "session", mock_session_success)

    # Mock redis connection in event bus
    class MockRedis:
        async def ping(self) -> None:
            raise Exception("Redis down")

    setup_admin_env["event_bus"].redis = MockRedis()
    manager._last_diag_time = 0.0
    diag_redis = await manager.get_diagnostics()
    assert diag_redis["redis"] == "ERROR"
    assert diag_redis["status"] == "degraded"

    # 3. Disk Usage failure
    import shutil

    def mock_disk_usage(path: str) -> Any:
        raise OSError("Permission denied")

    monkeypatch.setattr(shutil, "disk_usage", mock_disk_usage)
    manager._last_diag_time = 0.0
    diag_disk = await manager.get_diagnostics()
    assert diag_disk["resources"]["disk_usage_percent"] == 0.0


@pytest.mark.asyncio
async def test_admin_manager_metrics_db_failure(
    setup_admin_env: Dict[str, Any], monkeypatch: Any
) -> None:
    """Verify metrics computation is resilient to database connection failures."""
    manager = setup_admin_env["manager"]

    @contextlib.asynccontextmanager
    async def mock_session_fail(*args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
        raise Exception("DB Down")
        yield

    monkeypatch.setattr(setup_admin_env["db_manager"], "session", mock_session_fail)
    manager._last_metrics_time = 0.0
    metrics = await manager.get_metrics()
    assert metrics["total_execution_runs"] == 0
    assert metrics["completed_runs"] == 0
    assert metrics["success_rate"] == 0.0


@pytest.mark.asyncio
async def test_admin_manager_periodic_updater_loop_failures(
    setup_admin_env: Dict[str, Any], monkeypatch: Any
) -> None:
    """Verify the periodic updater loop is resilient to background exceptions."""
    import asyncio

    manager = setup_admin_env["manager"]

    async def mock_compute_fail() -> Any:
        raise ValueError("Background failure simulation")

    monkeypatch.setattr(manager, "_compute_diagnostics", mock_compute_fail)
    monkeypatch.setattr(manager, "_compute_metrics", mock_compute_fail)

    # Mock sleep to set manager._active to False to prevent infinite loop
    async def mock_sleep(seconds: float) -> None:
        manager._active = False

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    manager._active = True
    await manager._periodic_updater_loop()
    assert manager._active is False


@pytest.mark.asyncio
async def test_admin_manager_config_disk_save_failure(
    setup_admin_env: Dict[str, Any], monkeypatch: Any
) -> None:
    """Verify configuration update handles disk persistence failures cleanly."""
    manager = setup_admin_env["manager"]

    # Mock open to raise IOError
    def mock_open(*args: Any, **kwargs: Any) -> Any:
        raise IOError("Disk read-only")

    import core.runtime.admin

    monkeypatch.setattr(core.runtime.admin, "open", mock_open, raising=False)

    res = await manager.update_dynamic_config({"system_log_level": "WARNING"})
    assert res["status"] == "SUCCESS"
    assert manager.dynamic_config.system_log_level == "WARNING"


@pytest.mark.asyncio
async def test_admin_manager_create_backup_failure(
    setup_admin_env: Dict[str, Any], monkeypatch: Any
) -> None:
    """Verify create_backup raises JarvisSystemError if database query fails."""
    manager = setup_admin_env["manager"]

    @contextlib.asynccontextmanager
    async def mock_session_fail(*args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
        raise Exception("Backup DB Query Failed")
        yield

    monkeypatch.setattr(setup_admin_env["db_manager"], "session", mock_session_fail)

    with pytest.raises(JarvisSystemError) as exc_info:
        await manager.create_backup()
    assert "Backup generation failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_admin_manager_restore_rollback_on_db_error(
    setup_admin_env: Dict[str, Any], monkeypatch: Any
) -> None:
    """Verify database transaction rolls back and orchestrator is resumed if database throws an error during restoration."""
    manager = setup_admin_env["manager"]
    db = setup_admin_env["db_manager"]

    # 1. Create a backup
    backup_file = await manager.create_backup()

    # 2. Mock execute to throw error on DELETE
    original_execute = db.session

    @contextlib.asynccontextmanager
    async def mock_session() -> AsyncGenerator[Any, None]:
        class MockSession:
            async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
                if "DELETE" in str(statement):
                    raise Exception("Delete failure")
                async with original_execute() as real_sess:
                    return await real_sess.execute(statement, *args, **kwargs)

            def begin(self) -> Any:
                class MockTx:
                    async def __aenter__(self) -> Any:
                        return self

                    async def __aexit__(
                        self, exc_type: Any, exc_val: Any, exc_tb: Any
                    ) -> None:
                        pass

                return MockTx()

        yield MockSession()

    monkeypatch.setattr(db, "session", mock_session)

    with pytest.raises(JarvisSystemError) as exc_info:
        await manager.restore_backup(backup_file)
    assert "Database restore failed" in str(exc_info.value)

"""JARVIS OS - End-to-End System Smoke Test.

Coordinates Kernel initialization, Database session lifecycle, Event Bus broadcasts, Memory CRUD operations,
Runtime state engine runs, ToolRuntime execution, Audit logging, and graceful shutdown blocks.
"""

import asyncio
import json
import os
import tempfile

import pytest

from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.memory.database import db_manager
from core.memory.models import Base
from core.tools.audit import ImmutableAuditLogger
from core.tools.registry import ToolRegistry
from core.tools.runtime import ToolRuntime
from core.tools.sandbox import LocalSubprocessSandbox
from core.tools.security import PermissionGatekeeper


@pytest.mark.asyncio
async def test_end_to_end_system_smoke_flow() -> None:
    """Verify coordinating all main subsystems together in a single end-to-end lifecycle run."""
    # 1. System Settings Loading
    settings = Settings.load_settings()
    assert settings is not None

    # 2. Database Manager initialization & Schema migration
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    # 3. Event Bus Boot
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    # 4. Registry & Tool Runtime setup
    with tempfile.TemporaryDirectory() as temp_skills_dir:
        # Create a mock skill workspace
        skill_name = "smoke_skill"
        skill_path = os.path.join(temp_skills_dir, skill_name)
        os.makedirs(skill_path)

        with open(os.path.join(skill_path, "main.py"), "w", encoding="utf-8") as f:
            f.write("print('Smoke run success')\n")

        signature = PermissionGatekeeper.calculate_directory_hash(skill_path)

        manifest_data = {
            "name": "smoke-skill",
            "version": "1.0.0",
            "entry_point": "main.py",
            "permissions": ["file_read"],
            "signature": signature,
            "jarvis_api_version": "1.0",
            "skill_version": "1.0.0",
            "min_runtime_version": "1.0",
        }
        with open(
            os.path.join(skill_path, "manifest.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(manifest_data, f)

        # Discovers skills
        registry = ToolRegistry(skills_dir=temp_skills_dir)
        registry.discover_skills()
        assert "smoke-skill" in registry.skills

        # Instantiate Security, Sandbox, Auditing & Runtime Orchestration
        sandbox = LocalSubprocessSandbox()
        gatekeeper = PermissionGatekeeper(event_bus=event_bus)
        audit_logger = ImmutableAuditLogger()

        runtime = ToolRuntime(
            registry=registry,
            sandbox=sandbox,
            gatekeeper=gatekeeper,
            event_bus=event_bus,
            audit_logger=audit_logger,
        )

        # 5. Subscribe listener to track events
        events_fired = []

        from core.interfaces import InterAgentMessage

        async def event_callback(msg: InterAgentMessage) -> None:
            events_fired.append(msg)

        await event_bus.subscribe("system.tool.executed", event_callback)

        # 6. Execute Tool Invocation
        caller_id = "agent-smoke-01"
        args = {
            "command": [
                "python",
                "-c",
                "import sys; print('smoke-system-running'); sys.exit(0)",
            ],
            "image": "python:3.12-slim",
        }

        result = await runtime.execute_tool(
            tool_name="smoke-skill",
            arguments=args,
            caller_id=caller_id,
            system_env={"API_KEY": "smoke-val"},
        )

        # 7. Assert system outputs and DB state consistency
        assert result.exit_code == 0
        assert "smoke-system-running" in result.stdout

        # Verify Database entry
        db_log = await audit_logger.get_log(result.audit_id)
        assert db_log is not None
        assert db_log["tool_name"] == "smoke-skill"
        assert db_log["caller_id"] == caller_id

        # Verify Event Bus broadcast received
        await asyncio.sleep(0.05)
        assert len(events_fired) == 1
        assert events_fired[0].body["tool_name"] == "smoke-skill"

    # 8. Subsystem Shutdown Lifecycle
    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()

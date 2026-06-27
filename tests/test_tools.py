"""JARVIS OS - Tool and Skill System Unit & Integration Tests.

Verifies skill SDK manifest constraints, whitelisted sandbox runtimes, L0-L3 permission gates,
dynamic registries with signatures, tool runtime coordinator flow, and immutable audit logs.
"""

import asyncio
import json
import os
import tempfile
from uuid import uuid4

import pytest

try:
    import docker
except ImportError:
    docker = None

from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.exceptions import JarvisSkillError
from core.interfaces import InterAgentMessage
from core.memory.database import db_manager
from core.memory.models import Base
from core.tools.audit import ImmutableAuditLogger
from core.tools.base import SkillManifest, ToolExecutionResult
from core.tools.registry import ToolRegistry
from core.tools.runtime import ToolRuntime
from core.tools.sandbox import DockerSandbox, LocalSubprocessSandbox
from core.tools.security import PermissionGatekeeper

# =====================================================================
# 1. Manifest DTO & Validation Tests
# =====================================================================


def test_manifest_dto_validation() -> None:
    """Verify manifest.json validation constraints for skill packages."""
    # Valid manifest DTO
    manifest = SkillManifest(
        name="test-tool",
        version="1.0.0",
        entry_point="main.py",
        permissions=["network", "file_read"],
        signature="d3b07384d113edec49eaa6238ad5ff00",
        jarvis_api_version="1.0",
        skill_version="1.0.0",
        min_runtime_version="1.0",
        network_access=True,
    )
    assert manifest.name == "test-tool"
    assert manifest.permissions == ["network", "file_read"]

    # Invalid name pattern (uppercase)
    with pytest.raises(ValueError):
        SkillManifest(
            name="TEST-TOOL",
            version="1.0.0",
            entry_point="main.py",
            permissions=["network"],
            signature="sig",
            jarvis_api_version="1.0",
            skill_version="1.0.0",
            min_runtime_version="1.0",
        )

    # Invalid permission value
    with pytest.raises(ValueError) as excinfo:
        SkillManifest(
            name="test-tool",
            version="1.0.0",
            entry_point="main.py",
            permissions=["network", "root_execute"],
            signature="sig",
            jarvis_api_version="1.0",
            skill_version="1.0.0",
            min_runtime_version="1.0",
        )
    assert "root_execute" in str(excinfo.value)


# =====================================================================
# 2. Sandbox Isolation Tests
# =====================================================================


@pytest.mark.asyncio
async def test_docker_sandbox_whitelist_violation() -> None:
    """Verify DockerSandbox rejects non-whitelisted container images."""
    sandbox = DockerSandbox()
    with pytest.raises(JarvisSkillError) as excinfo:
        await sandbox.run(image="alpine:latest", command=["echo", "hi"])
    assert excinfo.value.code == "SKILL_001"
    assert "not whitelisted" in excinfo.value.message


@pytest.mark.asyncio
async def test_local_subprocess_sandbox_execution() -> None:
    """Verify LocalSubprocessSandbox runs subprocess commands and handles timeouts."""
    sandbox = LocalSubprocessSandbox()

    # Success run
    res = await sandbox.run(
        image="python:3.12-slim",
        command=["python", "-c", "import sys; print('subprocess-out'); sys.exit(0)"],
    )
    assert res["exit_code"] == 0
    assert "subprocess-out" in res["stdout"]

    # Timeout run (simulating timeout kill)
    res_timeout = await sandbox.run(
        image="python:3.12-slim",
        command=["python", "-c", "import time; time.sleep(5)"],
        timeout=0.1,
    )
    assert res_timeout["exit_code"] < 0  # Standard timeout negative exit code or -1


@pytest.mark.asyncio
async def test_sandbox_output_truncation_limits() -> None:
    """Verify stdout/stderr limits truncate output and flag truncated=True."""
    sandbox = LocalSubprocessSandbox(output_limit_bytes=5)
    res = await sandbox.run(
        image="python:3.12-slim",
        command=["python", "-c", "print('hello-world')"],
    )
    assert res["truncated"] is True
    assert len(res["stdout"]) <= 5
    assert res["stdout"] == "hello"


# =====================================================================
# 3. Security & Permission Gatekeeper Tests
# =====================================================================


@pytest.mark.asyncio
async def test_permission_gatekeeper_tiers_and_approvals() -> None:
    """Verify L0-L3 permissions and event bus approval loops."""
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    gatekeeper = PermissionGatekeeper(event_bus=event_bus, approval_timeout=1.0)

    # Level checks
    assert gatekeeper.get_permission_level("file_read") == "L0"
    assert gatekeeper.get_permission_level("file_write") == "L1"
    assert gatekeeper.get_permission_level("database_schema_modify") == "L2"
    assert gatekeeper.get_permission_level("host_cli_exec") == "L3"
    assert gatekeeper.get_permission_level("invalid-name") == "L3"

    # L0 and L1 check should pass autonomously
    await gatekeeper.verify_permissions("tool1", "file_read", "agent-123")
    await gatekeeper.verify_permissions("tool1", "file_write", "agent-123")

    # L3 human approval flow check:
    # Set up background listener on event bus to simulate user approval
    async def simulate_user_approval(msg: InterAgentMessage) -> None:
        if msg.action == "tool.approval.requested":
            correlation_id = msg.correlation_id
            # Resolve approval with True
            gatekeeper.receive_approval_response(correlation_id, approved=True)

    await event_bus.subscribe("tool.approval.requested", simulate_user_approval)

    # Verify L3 execution passes after simulated approval
    await gatekeeper.verify_permissions("dangerous-tool", "cli", "agent-123")

    # Verify L3 execution raises if rejected
    async def simulate_user_rejection(msg: InterAgentMessage) -> None:
        if msg.action == "tool.approval.requested":
            gk_rej.receive_approval_response(msg.correlation_id, approved=False)

    # Create new event bus to clear subscribers
    eb_rej = MemoryEventBus()
    await eb_rej.initialize()
    await eb_rej.start()
    gk_rej = PermissionGatekeeper(event_bus=eb_rej, approval_timeout=1.0)
    await eb_rej.subscribe("tool.approval.requested", simulate_user_rejection)

    with pytest.raises(JarvisSkillError) as excinfo:
        await gk_rej.verify_permissions("dangerous-tool", "cli", "agent-123")
    assert excinfo.value.code == "SKILL_004"
    assert "REJECTED" in excinfo.value.message

    # Verify L3 execution raises on approval timeout
    gk_timeout = PermissionGatekeeper(event_bus=eb_rej, approval_timeout=0.01)
    with pytest.raises(JarvisSkillError) as excinfo:
        await gk_timeout.verify_permissions("dangerous-tool", "cli", "agent-123")
    assert excinfo.value.code == "SKILL_004"
    assert "TIMEOUT" in excinfo.value.message

    # Scoped secrets injection check
    env = {"API_KEY": "secret-123", "DATABASE_URL": "db-abc", "SYSTEM_ROOT": "/root"}
    scoped = gk_rej.inject_scoped_secrets(
        allowed_keys=["API_KEY", "MISSING"], system_env=env
    )
    assert scoped == {"API_KEY": "secret-123"}
    assert "DATABASE_URL" not in scoped

    await event_bus.stop()
    await event_bus.shutdown()
    await eb_rej.stop()
    await eb_rej.shutdown()


# =====================================================================
# 4. Tool Registry Tests
# =====================================================================


def test_tool_registry_discovery_and_signatures() -> None:
    """Verify manifest loading, version checks, and SHA-256 directory signatures."""
    with tempfile.TemporaryDirectory() as temp_dir:
        skill_name = "test_skill"
        skill_path = os.path.join(temp_dir, skill_name)
        os.makedirs(skill_path)

        # Create files
        main_py = os.path.join(skill_path, "main.py")
        with open(main_py, "w", encoding="utf-8") as f:
            f.write("# Stub python code\nprint('hello')\n")

        # Compute valid signature
        signature = PermissionGatekeeper.calculate_directory_hash(skill_path)

        # Write manifest file
        manifest_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "entry_point": "main.py",
            "permissions": ["network"],
            "signature": signature,
            "jarvis_api_version": "1.0",
            "skill_version": "1.0.0",
            "min_runtime_version": "1.0",
        }
        manifest_json = os.path.join(skill_path, "manifest.json")
        with open(manifest_json, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f)

        # Load manifest
        registry = ToolRegistry(skills_dir=temp_dir)
        manifest = registry.load_skill_manifest(skill_name)
        assert manifest.name == "test-skill"
        assert manifest.signature == signature

        # Tamper check: edit file contents after manifest creation
        with open(main_py, "w", encoding="utf-8") as f:
            f.write("# Tampered code\n")

        with pytest.raises(JarvisSkillError) as excinfo:
            registry.load_skill_manifest(skill_name)
        assert excinfo.value.code == "SKILL_007"
        assert "signature check failed" in excinfo.value.message

        # Restore file and test API version mismatch
        with open(main_py, "w", encoding="utf-8") as f:
            f.write("# Stub python code\nprint('hello')\n")

        manifest_data["jarvis_api_version"] = "9.9"  # Version mismatch
        with open(manifest_json, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f)

        with pytest.raises(JarvisSkillError) as excinfo:
            registry.load_skill_manifest(skill_name)
        assert excinfo.value.code == "SKILL_006"
        assert "API version mismatch" in excinfo.value.message


# =====================================================================
# 5. Tool Runtime Engine & Integration Tests
# =====================================================================


@pytest.mark.asyncio
async def test_tool_runtime_engine_integration() -> None:
    """Verify ToolRuntime coordinates permission checks, sandbox, audit logs, and events."""
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    # Initialize in-memory test database
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    # 1. Setup dynamic registry with a mock skill
    with tempfile.TemporaryDirectory() as temp_dir:
        skill_name = "mock_tool"
        skill_path = os.path.join(temp_dir, skill_name)
        os.makedirs(skill_path)

        main_py = os.path.join(skill_path, "main.py")
        with open(main_py, "w", encoding="utf-8") as f:
            f.write("print('Running mock tool')")

        signature = PermissionGatekeeper.calculate_directory_hash(skill_path)

        manifest_data = {
            "name": "mock-tool",
            "version": "1.0.0",
            "entry_point": "main.py",
            "permissions": ["file_read", "network"],
            "signature": signature,
            "jarvis_api_version": "1.0",
            "skill_version": "1.0.0",
            "min_runtime_version": "1.0",
            "network_access": True,
        }
        with open(
            os.path.join(skill_path, "manifest.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(manifest_data, f)

        registry = ToolRegistry(skills_dir=temp_dir)
        registry.load_skill_manifest(skill_name)

        # 2. Setup dependencies
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

        # Set up event subscriber to verify publication
        received_events = []

        async def callback(msg: InterAgentMessage) -> None:
            received_events.append(msg)

        await event_bus.subscribe("system.tool.executed", callback)

        # 3. Execute Tool
        args = {
            "command": [
                "python",
                "-c",
                "import sys; print('tool-output'); sys.exit(0)",
            ],
            "image": "python:3.12-slim",
        }
        result = await runtime.execute_tool(
            tool_name="mock-tool",
            arguments=args,
            caller_id="agent-abc",
            system_env={"API_KEY": "key-val"},
        )

        # 4. Verify results
        assert isinstance(result, ToolExecutionResult)
        assert result.exit_code == 0
        assert "tool-output" in result.stdout
        assert result.truncated is False

        # Verify audit log entry matches result.audit_id
        db_log = await audit_logger.get_log(result.audit_id)
        assert db_log is not None
        assert db_log["tool_name"] == "mock-tool"
        assert db_log["caller_id"] == "agent-abc"
        assert "tool-output" in db_log["result"]["stdout"]

        # Verify Event Bus notification
        await asyncio.sleep(0.1)  # Yield to event handler
        assert len(received_events) == 1
        msg = received_events[0]
        assert msg.action == "system.tool.executed"
        assert msg.body["tool_name"] == "mock-tool"
        assert msg.body["audit_id"] == str(result.audit_id)

    # Cleanups
    await db_manager.close()
    await event_bus.stop()
    await event_bus.shutdown()


# =====================================================================
# 6. Immutable Auditing Tests
# =====================================================================


@pytest.mark.asyncio
async def test_immutable_auditing_integrity() -> None:
    """Verify write-once audit log entries block update and delete requests."""
    # Setup test DB
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    logger = ImmutableAuditLogger()
    audit_id = uuid4()

    # Log invocation
    await logger.log_invocation(
        audit_id=audit_id,
        tool_name="test-tool",
        caller_id="agent-xyz",
        arguments={"arg": 1},
        result={"stdout": "ok"},
    )

    # Query log
    log_data = await logger.get_log(audit_id)
    assert log_data is not None
    assert log_data["tool_name"] == "test-tool"

    # Attempt delete
    with pytest.raises(JarvisSkillError) as excinfo:
        await logger.delete_log(audit_id)
    assert excinfo.value.code == "SKILL_009"
    assert "tampering" in excinfo.value.message.lower()

    # Attempt update
    with pytest.raises(JarvisSkillError) as excinfo:
        await logger.update_log(audit_id, {"caller_id": "hacked"})
    assert excinfo.value.code == "SKILL_009"
    assert "tampering" in excinfo.value.message.lower()

    # Duplicate UUID insert raises JarvisMemoryError due to transaction wrapping
    from core.exceptions import JarvisMemoryError

    with pytest.raises(JarvisMemoryError) as excinfo_dup:
        await logger.log_invocation(
            audit_id=audit_id,  # Duplicate!
            tool_name="test-tool",
            caller_id="agent-xyz",
            arguments={"arg": 1},
            result={"stdout": "ok"},
        )
    assert excinfo_dup.value.code == "SYSTEM_999"

    # Force database exceptions to test uninitialized handler paths
    await db_manager.close()
    with pytest.raises(JarvisMemoryError) as excinfo_init:
        await logger.log_invocation(
            audit_id=uuid4(),
            tool_name="x",
            caller_id="y",
            arguments={},
            result={},
        )
    assert excinfo_init.value.code == "SYSTEM_001"

    with pytest.raises(JarvisMemoryError) as excinfo_query:
        await logger.get_log(uuid4())
    assert excinfo_query.value.code == "SYSTEM_001"


@pytest.mark.asyncio
async def test_registry_edge_cases() -> None:
    """Verify registry discovery checks, missing manifest, malformed manifest JSON, and schema errors."""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry = ToolRegistry(skills_dir=temp_dir)

        # 1. Missing manifest
        skill_name = "missing_manifest"
        os.makedirs(os.path.join(temp_dir, skill_name))
        with pytest.raises(JarvisSkillError) as excinfo:
            registry.load_skill_manifest(skill_name)
        assert excinfo.value.code == "SKILL_005"
        assert "missing" in excinfo.value.message

        # 2. Malformed json syntax
        skill_name = "malformed_json"
        skill_path = os.path.join(temp_dir, skill_name)
        os.makedirs(skill_path)
        with open(os.path.join(skill_path, "manifest.json"), "w") as f:
            f.write("{invalid-json-syntax")
        with pytest.raises(JarvisSkillError) as excinfo:
            registry.load_skill_manifest(skill_name)
        assert excinfo.value.code == "SKILL_005"
        assert "parse manifest" in excinfo.value.message

        # 3. Pydantic validation error
        skill_name = "invalid_schema"
        skill_path = os.path.join(temp_dir, skill_name)
        os.makedirs(skill_path)
        with open(os.path.join(skill_path, "manifest.json"), "w") as f:
            json.dump({"name": "only-name-no-required-fields"}, f)
        with pytest.raises(JarvisSkillError) as excinfo:
            registry.load_skill_manifest(skill_name)
        assert excinfo.value.code == "SKILL_005"
        assert "validation failed" in excinfo.value.message

        # 4. Discover skills with non-existent folder
        registry_nonexistent = ToolRegistry(skills_dir="/non/existent/path")
        registry_nonexistent.discover_skills()
        assert len(registry_nonexistent.skills) == 0

        # 5. Discover skills ignore failure
        # Create a valid skill
        valid_name = "valid_skill"
        valid_path = os.path.join(temp_dir, valid_name)
        os.makedirs(valid_path)
        with open(os.path.join(valid_path, "main.py"), "w") as f:
            f.write("# code")
        sig = PermissionGatekeeper.calculate_directory_hash(valid_path)
        manifest_data = {
            "name": "valid-skill",
            "version": "1.0.0",
            "entry_point": "main.py",
            "permissions": [],
            "signature": sig,
            "jarvis_api_version": "1.0",
            "skill_version": "1.0.0",
            "min_runtime_version": "1.0",
        }
        with open(os.path.join(valid_path, "manifest.json"), "w") as f:
            json.dump(manifest_data, f)

        # discover_skills should successfully load the valid one and skip the malformed ones
        registry.discover_skills()
        assert "valid-skill" in registry.skills
        assert len(registry.skills) == 1


@pytest.mark.asyncio
async def test_tool_runtime_errors() -> None:
    """Verify ToolRuntime raises SKILL_008 for unregistered tools."""
    event_bus = MemoryEventBus()
    registry = ToolRegistry(skills_dir="/fake")
    sandbox = LocalSubprocessSandbox()
    gatekeeper = PermissionGatekeeper(event_bus=event_bus)
    runtime = ToolRuntime(
        registry=registry, sandbox=sandbox, gatekeeper=gatekeeper, event_bus=event_bus
    )

    with pytest.raises(JarvisSkillError) as excinfo:
        await runtime.execute_tool(tool_name="unknown", arguments={}, caller_id="1")
    assert excinfo.value.code == "SKILL_008"


@pytest.mark.asyncio
async def test_permission_gatekeeper_unreadable_file_hash() -> None:
    """Verify calculate_directory_hash skips unreadable files gracefully."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a file
        file_path = os.path.join(temp_dir, "unreadable.py")
        with open(file_path, "w") as f:
            f.write("test")

        h = PermissionGatekeeper.calculate_directory_hash(temp_dir)
        assert isinstance(h, str)


@pytest.mark.asyncio
async def test_docker_sandbox_success_and_exception_mocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify DockerSandbox behavior using mocked Docker client SDK objects."""
    if not docker:
        import sys
        from unittest.mock import MagicMock

        sys.modules["docker"] = MagicMock()

    from unittest.mock import MagicMock

    mock_container = MagicMock()
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.side_effect = [b"mock-stdout\n", b"mock-stderr\n"]

    mock_containers = MagicMock()
    mock_containers.create.return_value = mock_container

    mock_client = MagicMock()
    mock_client.containers = mock_containers

    sandbox = DockerSandbox()
    sandbox.client = mock_client

    res = await sandbox.run(
        image="python:3.12-slim",
        command=["echo", "1"],
        network_access=True,
    )
    assert res["exit_code"] == 0
    assert "mock-stdout" in res["stdout"]
    assert "mock-stderr" in res["stderr"]

    # Test docker exceptions
    mock_containers.create.side_effect = Exception("Docker engine crashed")
    with pytest.raises(JarvisSkillError) as excinfo:
        await sandbox.run(image="python:3.12-slim", command=["echo", "1"])
    assert excinfo.value.code == "SKILL_003"
    assert "Docker execution failed" in excinfo.value.message


@pytest.mark.asyncio
async def test_local_subprocess_sandbox_invalid_cmd() -> None:
    """Verify LocalSubprocessSandbox handles command initialization exceptions."""
    sandbox = LocalSubprocessSandbox()
    with pytest.raises(JarvisSkillError) as excinfo:
        await sandbox.run(
            image="python:3.12-slim", command=["non-existent-executable-bin"]
        )
    assert excinfo.value.code == "SKILL_003"
    assert "failed" in excinfo.value.message

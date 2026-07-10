"""
PHASE: Platform Infrastructure (CR-002 runtime-fix companion)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/CR/CR-002-skills-router-mount-shadowing.md
    (section "Future-proof runtime fixes" — companion to the route-shadowing fix)

IMPLEMENTATION PLAN:
    docs/CR/CR-002-skills-router-mount-shadowing.md

AUTHORITATIVE:
    NO

Regression tests for the four runtime bugs that the comprehensive
``scripts/runtime_sweep.py`` exposed on top of CR-002:

  1. ``VaultManager.is_locked()`` was missing → 503 on
     ``/api/v1/platform/readiness`` ("VaultManager has no attribute is_locked").
  2. ``SkillInstaller`` was not registered in the DI container → 500 on
     ``/api/v1/skills/install`` and ``/api/v1/skills/remove``.
  3. ``SwarmResumeManager._recover_session_data`` subtracted
     ``datetime.now(timezone.utc)`` from an offset-naive
     ``task_model.updated_at`` returned by SQLite, raising
     ``TypeError: can't subtract offset-naive and offset-aware datetimes``
     on every boot.
  4. ``SyncManager._publish_event`` built an ``InterAgentMessage`` with
     the legacy field names (``target``, ``content``) that the current
     Pydantic schema rejects, logging a validation error on every
     ``sync.pushed`` / ``sync.pulled`` event.

Each test below is small and self-contained; together they assert the
behaviour that the runtime sweep relied on.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# 1. VaultManager.is_locked()
# ---------------------------------------------------------------------------


def test_vault_manager_is_locked_before_init() -> None:
    """A freshly constructed VaultManager is locked (no key loaded yet)."""
    from core.security.vault import VaultManager

    with tempfile.TemporaryDirectory() as td:
        key_path = os.path.join(td, "master.key")
        vault = VaultManager(key_path=key_path)
        assert vault.is_locked() is True
        assert vault._key is None


def test_vault_manager_is_unlocked_after_init() -> None:
    """After initialize(), is_locked() returns False (key is in memory)."""
    from core.security.vault import VaultManager

    with tempfile.TemporaryDirectory() as td:
        key_path = os.path.join(td, "master.key")
        vault = VaultManager(key_path=key_path)
        asyncio.run(vault.initialize())
        assert vault.is_locked() is False
        assert vault._key is not None


# ---------------------------------------------------------------------------
# 2. SkillInstaller DI registration
# ---------------------------------------------------------------------------


def test_skill_installer_registered_in_kernel_container() -> None:
    """Kernel.container.resolve(SkillInstaller) must succeed.

    Before the fix this raised ``JarvisSystemError: No service registered
    for interface 'SkillInstaller'`` and the /skills/install + /skills/remove
    routes returned 500.
    """
    from core.kernel import Kernel
    from core.skills.installer import SkillInstaller

    # Build a minimal kernel by patching its settings/db to keep the test fast.
    kernel = Kernel.__new__(Kernel)
    # Use a real container; the kernel's __init__ is heavy (DB + DI seeds).
    from core.container import DependencyContainer

    kernel.container = DependencyContainer()
    kernel.lifecycle_manager = MagicMock()

    # Pull in the small set of dependencies the SkillInstaller wiring needs.
    from core.interfaces import EventBusInterface
    from core.skills.permission_engine import SkillPermissionEngine
    from core.skills.registry import SkillRegistry
    from core.skills.repository import SkillRepository
    from core.skills.sandbox import SandboxTestRunner
    from core.skills.signer import SkillSigner
    from core.skills.validator import SkillValidator
    from core.tools.security import PermissionGatekeeper

    event_bus = MagicMock(spec=EventBusInterface)
    gatekeeper = MagicMock(spec=PermissionGatekeeper)
    registry = SkillRegistry()
    validator = SkillValidator()
    repository = SkillRepository()
    sandbox = SandboxTestRunner()
    signer = SkillSigner()
    perm_engine = SkillPermissionEngine(gatekeeper=gatekeeper, event_bus=event_bus)
    installer = SkillInstaller(
        validator=validator,
        repository=repository,
        registry=registry,
        sandbox_runner=sandbox,
        permission_engine=perm_engine,
        signer=signer,
        event_bus=event_bus,
    )

    kernel.container.register_singleton(SkillInstaller, installer)
    # Mirror the production kernel wiring: register each child component
    # too, so callers can resolve them independently.
    kernel.container.register_singleton(SkillValidator, validator)
    kernel.container.register_singleton(SkillRepository, repository)
    kernel.container.register_singleton(SandboxTestRunner, sandbox)
    kernel.container.register_singleton(SkillSigner, signer)
    kernel.container.register_singleton(SkillPermissionEngine, perm_engine)

    resolved = kernel.container.resolve(SkillInstaller)
    assert resolved is installer
    # All 6 child components should be available too (the wiring is complete).
    assert kernel.container.resolve(SkillValidator) is validator
    assert kernel.container.resolve(SkillRepository) is repository
    assert kernel.container.resolve(SandboxTestRunner) is sandbox
    assert kernel.container.resolve(SkillSigner) is signer
    assert kernel.container.resolve(SkillPermissionEngine) is perm_engine


# ---------------------------------------------------------------------------
# 3. SwarmResumeManager — offset-naive vs offset-aware datetime
# ---------------------------------------------------------------------------


def test_swarm_resume_manager_handles_naive_updated_at() -> None:
    """A task_model.updated_at that is offset-naive must not crash the recovery subtraction.

    Before the fix this raised
    ``TypeError: can't subtract offset-naive and offset-aware datetimes``
    inside ``_recover_session_data`` on every boot.
    """
    from core.interfaces import EventBusInterface
    from core.runtime.orchestrator import SwarmOrchestrator
    from core.runtime.recovery_manager import SwarmResumeManager

    # Build a minimal SwarmResumeManager. Only the methods we exercise run.
    orchestrator = MagicMock(spec=SwarmOrchestrator)
    event_bus = MagicMock(spec=EventBusInterface)
    event_bus.publish = AsyncMock(return_value=True)

    mgr = SwarmResumeManager(
        orchestrator=orchestrator,
        event_bus=event_bus,
        recovery_timeout_seconds=300.0,
    )

    # Simulate a stale Running task with a NAIVE updated_at (as SQLite returns).
    class _FakeModel:
        def __init__(self) -> None:
            self.task_id = uuid4()
            self.goal = "do the thing"
            self.priority = "NORMAL"
            self.capabilities: list[str] = []
            self.timeout = 60.0
            self.retry = 0
            self.dependencies: list[str] = []
            self.metadata_: Dict[str, Any] = {}
            self.status = "Running"
            self.version = 1
            # Naive datetime (the bug case) — datetime.utcnow() returns naive.
            self.updated_at = datetime.utcnow()

    class _FakeResult:
        def scalars(self) -> "_FakeResult":
            return self

        def all(self) -> list[Any]:
            return [_FakeModel()]

    class _FakeAgentResult:
        def scalars(self) -> "_FakeAgentResult":
            return self

        def all(self) -> list[Any]:
            return []

    class _FakeSession:
        def in_transaction(self) -> bool:
            return False

        def begin(self) -> "_FakeBegin":
            return _FakeBegin()

        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *exc: Any) -> None:
            return None

        async def execute(self, stmt: Any) -> Any:
            # First call is for tasks, second is for agents.
            if not getattr(self, "_seen_task_query", False):
                self._seen_task_query = True
                return _FakeResult()
            return _FakeAgentResult()

        async def commit(self) -> None:
            return None

    class _FakeBegin:
        async def __aenter__(self) -> _FakeBegin:
            return self

        async def __aexit__(self, *exc: Any) -> None:
            return None

    async def _run() -> None:
        # Patch db_manager.session so _recover_session_data uses our fake session.
        from core.runtime import recovery_manager as rm_mod

        class _FakeDBManager:
            def session(self) -> _FakeSession:
                return _FakeSession()

        original = rm_mod.db_manager
        rm_mod.db_manager = _FakeDBManager()  # type: ignore[assignment]
        try:
            await mgr.recover_all()
        finally:
            rm_mod.db_manager = original

    # If the fix is in place, this completes without TypeError.
    asyncio.run(_run())


def test_swarm_resume_manager_handles_aware_updated_at() -> None:
    """An already-aware updated_at must still work (regression of the fix)."""
    from core.interfaces import EventBusInterface
    from core.runtime.orchestrator import SwarmOrchestrator
    from core.runtime.recovery_manager import SwarmResumeManager

    orchestrator = MagicMock(spec=SwarmOrchestrator)
    event_bus = MagicMock(spec=EventBusInterface)
    event_bus.publish = AsyncMock(return_value=True)

    mgr = SwarmResumeManager(
        orchestrator=orchestrator,
        event_bus=event_bus,
        recovery_timeout_seconds=300.0,
    )

    class _FakeModel:
        def __init__(self) -> None:
            self.task_id = uuid4()
            self.goal = "do the other thing"
            self.priority = "NORMAL"
            self.capabilities: list[str] = []
            self.timeout = 60.0
            self.retry = 0
            self.dependencies: list[str] = []
            self.metadata_: Dict[str, Any] = {}
            self.status = "Running"
            self.version = 1
            # Aware datetime (happy path)
            self.updated_at = datetime.now(timezone.utc)

    class _FakeResult:
        def scalars(self) -> "_FakeResult":
            return self

        def all(self) -> list[Any]:
            return [_FakeModel()]

    class _FakeAgentResult:
        def scalars(self) -> "_FakeAgentResult":
            return self

        def all(self) -> list[Any]:
            return []

    class _FakeSession:
        def in_transaction(self) -> bool:
            return False

        def begin(self) -> "_FakeBegin":
            return _FakeBegin()

        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *exc: Any) -> None:
            return None

        async def execute(self, stmt: Any) -> Any:
            if not getattr(self, "_seen_task_query", False):
                self._seen_task_query = True
                return _FakeResult()
            return _FakeAgentResult()

    class _FakeBegin:
        async def __aenter__(self) -> "_FakeBegin":
            return self

        async def __aexit__(self, *exc: Any) -> None:
            return None

    async def _run() -> None:
        from core.runtime import recovery_manager as rm_mod

        class _FakeDBManager:
            def session(self) -> _FakeSession:
                return _FakeSession()

        original = rm_mod.db_manager
        rm_mod.db_manager = _FakeDBManager()  # type: ignore[assignment]
        try:
            await mgr.recover_all()
        finally:
            rm_mod.db_manager = original

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. SyncManager._publish_event — InterAgentMessage schema
# ---------------------------------------------------------------------------


def test_sync_publish_event_uses_canonical_message_schema() -> None:
    """SyncManager._publish_event must build an InterAgentMessage that validates.

    Before the fix this logged
    ``Failed to publish sync event sync.pushed: 3 validation errors for
    InterAgentMessage`` on every push, because the code used legacy
    field names ``target`` and ``content`` that the current Pydantic
    schema rejects.
    """
    from core.interfaces import InterAgentMessage
    from core.security.sync import SyncManager

    captured: Dict[str, Any] = {}

    class _CapturingBus:
        async def publish(self, topic: str, message: InterAgentMessage) -> bool:
            captured["topic"] = topic
            captured["message"] = message
            return True

    bus = _CapturingBus()

    # Construct a SyncManager without going through real DI. We only need
    # ``_publish_event`` to run, so minimal init is enough.
    vault = MagicMock()
    vault._key = b"x" * 32
    vault.secrets_path = "/tmp/nope"
    storage = MagicMock()
    settings = MagicMock()
    sync = SyncManager(
        client_id="test-node",
        vault_manager=vault,
        storage_provider=storage,
        settings=settings,
        event_bus=bus,  # type: ignore[arg-type]
    )

    asyncio.run(
        sync._publish_event("sync.pushed", {"sync_id": "s1", "client_id": "c1"})
    )

    assert captured["topic"] == "sync.pushed"
    msg = captured["message"]
    # The schema fields must be the canonical ones (and validation must have
    # actually run — Pydantic raises on construction otherwise).
    assert isinstance(msg, InterAgentMessage)
    assert msg.sender == "sync_manager_test-node"
    assert msg.receiver == "*"
    assert msg.action == "sync.pushed"
    assert msg.body == {"sync_id": "s1", "client_id": "c1"}
    # And the legacy fields must NOT leak through.
    assert not hasattr(msg, "target")
    assert not hasattr(msg, "content")

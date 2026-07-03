"""Phase 18 M6 permission engine contract tests (pure, no I/O)."""

from unittest.mock import AsyncMock

import pytest

from core.skills.permission_engine import (
    SkillPermissionEngine,
)
from core.tools.security import PermissionGatekeeper


class _FakeEventBus:
    """Minimal EventBusInterface stub for testing."""

    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    async def publish(self, topic: str, message: object) -> bool:
        self.published.append((topic, message))
        return True

    async def subscribe(self, topic: str, callback: object) -> str:
        return "sub-1"

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


def _make_gatekeeper() -> PermissionGatekeeper:
    return PermissionGatekeeper(event_bus=_FakeEventBus())


class TestPermissionEvaluation:
    def test_l0_l1_auto_approved(self) -> None:
        gatekeeper = _make_gatekeeper()
        engine = SkillPermissionEngine(gatekeeper, _FakeEventBus())

        result = engine.evaluate(["file_read", "file_write"])

        assert result.decision == "AUTO_APPROVED"
        assert result.highest_level == "L1"
        assert result.required_approvals == []

    def test_l2_requires_approval(self) -> None:
        gatekeeper = _make_gatekeeper()
        engine = SkillPermissionEngine(gatekeeper, _FakeEventBus())

        result = engine.evaluate(["database_schema_modify"])

        assert result.decision == "AWAITING_APPROVAL"
        assert result.highest_level == "L2"
        assert "database_schema_modify" in result.required_approvals

    def test_l3_requires_approval(self) -> None:
        gatekeeper = _make_gatekeeper()
        engine = SkillPermissionEngine(gatekeeper, _FakeEventBus())

        result = engine.evaluate(["host_cli_exec", "file_write"])

        assert result.decision == "AWAITING_APPROVAL"
        assert result.highest_level == "L3"
        assert "host_cli_exec" in result.required_approvals

    def test_mixed_permissions_highest_wins(self) -> None:
        gatekeeper = _make_gatekeeper()
        engine = SkillPermissionEngine(gatekeeper, _FakeEventBus())

        result = engine.evaluate(["file_read", "browser", "host_cli_exec"])

        assert result.decision == "AWAITING_APPROVAL"
        assert result.highest_level == "L3"
        assert len(result.required_approvals) == 2  # browser (L2), host_cli_exec (L3)

    def test_empty_permissions_rejected(self) -> None:
        gatekeeper = _make_gatekeeper()
        engine = SkillPermissionEngine(gatekeeper, _FakeEventBus())

        result = engine.evaluate([])

        assert result.decision == "REJECTED"
        assert result.highest_level == "L0"
        assert result.required_approvals == []


class TestRequestApprovals:
    @pytest.mark.asyncio
    async def test_auto_approved_returns_immediately(self) -> None:
        gatekeeper = _make_gatekeeper()
        event_bus = _FakeEventBus()
        engine = SkillPermissionEngine(gatekeeper, event_bus)

        decision = await engine.request_approvals(
            "skill-1", "caller", ["file_read", "network"]
        )

        assert decision == "AUTO_APPROVED"
        assert len(event_bus.published) == 0  # No events for auto-approved

    @pytest.mark.asyncio
    async def test_l2_triggers_approval_flow(self) -> None:
        gatekeeper = _make_gatekeeper()
        event_bus = _FakeEventBus()
        engine = SkillPermissionEngine(gatekeeper, event_bus)

        # Mock verify_permissions to succeed (approval granted)
        gatekeeper.verify_permissions = AsyncMock(return_value=None)

        decision = await engine.request_approvals(
            "skill-2", "caller-2", ["database_schema_modify"]
        )

        assert decision == "AUTO_APPROVED"
        # Should have published skill.approval.waiting and skill.approval.granted
        topics = [topic for topic, _ in event_bus.published]
        assert "skill.approval.waiting" in topics
        assert "skill.approval.granted" in topics

    @pytest.mark.asyncio
    async def test_l3_triggers_approval_flow(self) -> None:
        gatekeeper = _make_gatekeeper()
        event_bus = _FakeEventBus()
        engine = SkillPermissionEngine(gatekeeper, event_bus)

        gatekeeper.verify_permissions = AsyncMock(return_value=None)

        decision = await engine.request_approvals(
            "skill-3", "caller-3", ["host_cli_exec"]
        )

        assert decision == "AUTO_APPROVED"
        topics = [topic for topic, _ in event_bus.published]
        assert "skill.approval.waiting" in topics
        assert "skill.approval.granted" in topics

    @pytest.mark.asyncio
    async def test_rejected_on_approval_failure(self) -> None:
        gatekeeper = _make_gatekeeper()
        event_bus = _FakeEventBus()
        engine = SkillPermissionEngine(gatekeeper, event_bus)

        # Mock verify_permissions to raise (rejection/timeout)
        gatekeeper.verify_permissions = AsyncMock(side_effect=Exception("rejected"))

        decision = await engine.request_approvals("skill-4", "caller-4", ["cli"])

        assert decision == "REJECTED"


class TestGatekeeperIntegration:
    def test_get_permission_level_mapping(self) -> None:
        gatekeeper = _make_gatekeeper()

        assert gatekeeper.get_permission_level("file_read") == "L0"
        assert gatekeeper.get_permission_level("database_query") == "L0"
        assert gatekeeper.get_permission_level("network") == "L0"

        assert gatekeeper.get_permission_level("file_write") == "L1"
        assert gatekeeper.get_permission_level("cache_write") == "L1"

        assert gatekeeper.get_permission_level("database_schema_modify") == "L2"
        assert gatekeeper.get_permission_level("config_write") == "L2"

        assert gatekeeper.get_permission_level("host_cli_exec") == "L3"
        assert gatekeeper.get_permission_level("browser_payment") == "L3"
        assert gatekeeper.get_permission_level("cli") == "L3"

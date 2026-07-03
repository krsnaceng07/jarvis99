"""Phase 18 M8 SkillInstaller end-to-end contract tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.exceptions import JarvisSkillError
from core.skills.download_dto import DownloadedPackage
from core.skills.dto import SkillManifest
from core.skills.installer import SkillInstaller
from core.skills.permission_engine import SkillPermissionEngine
from core.skills.registry import SkillRegistry
from core.skills.sandbox import SandboxTestRunner
from core.skills.sandbox_dto import SandboxResult
from core.skills.signer import SkillSigner
from core.skills.validator import SkillValidator
from core.tools.security import PermissionGatekeeper

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeEventBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, Any]] = []

    async def publish(self, topic: str, message: Any) -> bool:
        self.published.append((topic, message))
        return True

    async def subscribe(self, topic: str, callback: Any) -> str:
        return "sub-1"

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class _InMemoryRepository:
    """In-memory repository for testing without SQLAlchemy sessions."""

    def __init__(self) -> None:
        self._skills: dict[str, Any] = {}
        self._skills_by_name: dict[str, str] = {}
        self._versions: dict[str, list[Any]] = {}
        self._capabilities: dict[str, list[str]] = {}

    async def get_skill_by_name(self, name: str, session: Any = None) -> Any:
        skill_id = self._skills_by_name.get(name)
        if skill_id:
            return self._skills.get(skill_id)
        for model in self._skills.values():
            if model.name == name:
                return model
        return None

    async def get_skill_by_id(self, skill_id: str, session: Any = None) -> Any:
        return self._skills.get(skill_id)

    async def save_installed_skill(self, skill: Any, session: Any = None) -> None:
        self._skills[skill.id] = skill
        self._skills_by_name[skill.name] = skill.id

    async def remove_skill(self, skill_id: str, session: Any = None) -> Any:
        model = self._skills.get(skill_id)
        if model:
            model.status = "REMOVED"
        return model

    async def update_skill_metadata(
        self, skill_id: str, session: Any = None, **kwargs: Any
    ) -> Any:
        model = self._skills.get(skill_id)
        if model is None:
            return None
        for k, v in kwargs.items():
            if v is not None and hasattr(model, k):
                setattr(model, k, v)
        return model

    async def save_skill_capabilities(
        self, skill_id: str, capability_keys: list[str], session: Any = None
    ) -> None:
        self._capabilities[skill_id] = capability_keys

    async def append_skill_version(
        self,
        skill_id: str,
        version: str,
        status: str,
        session: Any = None,
        reason: str | None = None,
    ) -> None:
        self._versions.setdefault(skill_id, []).append(
            type("V", (), {"version": version, "status": status})()
        )


def _valid_manifest() -> dict[str, Any]:
    return {
        "id": "testskill",
        "name": "testskill",
        "version": "1.0.0",
        "author": "tester",
        "description": "A test skill",
        "entrypoint": "main.py",
        "permissions": ["file_read", "network"],
        "dependencies": [],
        "signature": "a" * 64,
        "checksum": "b" * 64,
        "jarvis_api_version": "0.8",
        "min_runtime_version": "0.8",
        "approval_level": "L0",
        "trust_level": "OFFICIAL",
        "capabilities": [{"key": "test.skill.execute"}],
        "compatibility": {
            "platforms": ["windows", "linux"],
            "architectures": ["x64"],
            "python": ">=3.11",
            "jarvis_runtime": ">=0.8",
        },
        "limits": {
            "memory": "512MB",
            "cpu": "1",
            "timeout": 60,
            "network": False,
            "filesystem": "sandbox",
        },
        "isolation": "container",
    }


def _downloaded_package(tmp_path: Path) -> DownloadedPackage:
    import zipfile

    pkg = tmp_path / "test_skill.zip"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("main.py", "print('hello')")
        zf.writestr("tests/test_main.py", "def test_ok(): assert True")
        zf.writestr("manifest.json", "{}")
    return DownloadedPackage(
        skill_id="testskill",
        version="1.0.0",
        source_kind="local_package",
        package_path=str(pkg),
        checksum="b" * 64,
        size_bytes=pkg.stat().st_size,
    )


def _make_installer(
    tmp_path: Path,
    *,
    validate_fail: bool = False,
    sandbox_fail: bool = False,
    permission_fail: bool = False,
    sign_fail: bool = False,
    already_installed: bool = False,
) -> tuple[SkillInstaller, _FakeEventBus, SkillRegistry, _InMemoryRepository]:
    event_bus = _FakeEventBus()
    gatekeeper = PermissionGatekeeper(event_bus=event_bus)
    validator = SkillValidator()
    repository = _InMemoryRepository()
    registry = SkillRegistry()

    # Use a mock sandbox that returns PASSED without Docker
    sandbox = MagicMock(spec=SandboxTestRunner)
    if sandbox_fail:
        sandbox.run = AsyncMock(
            return_value=SandboxResult(
                status="FAILED",
                exit_code=1,
                duration_ms=0,
                memory_peak_mb=0,
                cpu_time_ms=0,
                stderr="sandbox forced fail",
            )
        )
    else:
        sandbox.run = AsyncMock(
            return_value=SandboxResult(
                status="PASSED",
                exit_code=0,
                duration_ms=100,
                memory_peak_mb=64,
                cpu_time_ms=50,
            )
        )

    permission_engine = SkillPermissionEngine(gatekeeper, event_bus)
    signer = SkillSigner(trusted_root_fingerprint="jarvis-root-v1")

    if validate_fail:

        def _validate_fail(payload: dict) -> SkillManifest:
            raise JarvisSkillError(code="SKILL_V001", message="Validation forced fail")

        validator.validate_manifest = _validate_fail  # type: ignore[assignment]

    if sign_fail:

        def _sign_fail(
            skill_dir: Any, expected_signature: Any, publisher_certificate: Any = None
        ) -> Any:
            from core.skills.signer import SignatureVerification

            return SignatureVerification(
                decision="TAMPERED",
                directory_hash="",
                expected_signature=expected_signature,
                message="forced tamper",
            )

        signer.verify = _sign_fail  # type: ignore[assignment]
    else:

        def _sign_pass(
            skill_dir: Any, expected_signature: Any, publisher_certificate: Any = None
        ) -> Any:
            from core.skills.signer import SignatureVerification

            return SignatureVerification(
                decision="VALID",
                directory_hash=expected_signature,
                expected_signature=expected_signature,
                message="Signature verified.",
            )

        signer.verify = _sign_pass  # type: ignore[assignment]

    if already_installed:
        from core.skills.models import InstalledSkillModel

        model = InstalledSkillModel(
            id="testskill",
            name="testskill",
            version="0.9.0",
            status="ACTIVE",
            trust_level="OFFICIAL",
            manifest_json="{}",
            checksum="b" * 64,
            signature="a" * 64,
            approval_level="L0",
        )
        repository._skills["testskill"] = model
        # Also store by name for name-based lookup
        repository._skills_by_name = {"testskill": "testskill"}

    installer = SkillInstaller(
        validator=validator,
        repository=repository,
        registry=registry,
        sandbox_runner=sandbox,
        permission_engine=permission_engine,
        signer=signer,
        event_bus=event_bus,
        skill_dir=tmp_path,
    )

    return installer, event_bus, registry, repository


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInstallSuccess:
    @pytest.mark.asyncio
    async def test_full_install_lifecycle(self, tmp_path: Path) -> None:
        installer, event_bus, registry, _ = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        result = await installer.install(payload, pkg, caller_id="user-1")

        assert result.success is True
        assert result.state == "ACTIVE"
        assert result.name == "testskill"

        # Verify registry has the skill
        registered = registry.get_by_id("testskill")
        assert registered is not None
        assert registered.version == "1.0.0"

        # Verify events emitted
        topics = [t for t, _ in event_bus.published]
        assert "skill.installed" in topics

    @pytest.mark.asyncio
    async def test_install_registers_capabilities(self, tmp_path: Path) -> None:
        installer, _, registry, _ = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        await installer.install(payload, pkg, caller_id="user-1")

        found = registry.find_by_capability("test.skill.execute")
        assert len(found) == 1
        assert found[0].id == "testskill"


class TestInstallRejection:
    @pytest.mark.asyncio
    async def test_already_installed_without_force(self, tmp_path: Path) -> None:
        installer, _, _, _ = _make_installer(tmp_path, already_installed=True)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        result = await installer.install(payload, pkg, caller_id="user-1", force=False)

        assert result.success is False
        assert "SKILL_I002" in result.message

    @pytest.mark.asyncio
    async def test_force_overwrites_existing(self, tmp_path: Path) -> None:
        installer, _, registry, _ = _make_installer(tmp_path, already_installed=True)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        result = await installer.install(payload, pkg, caller_id="user-1", force=True)

        assert result.success is True
        assert registry.get_by_id("testskill").version == "1.0.0"

    @pytest.mark.asyncio
    async def test_validation_failure(self, tmp_path: Path) -> None:
        installer, _, _, _ = _make_installer(tmp_path, validate_fail=True)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        result = await installer.install(payload, pkg, caller_id="user-1")

        assert result.success is False
        assert result.state == "FAILED"

    @pytest.mark.asyncio
    async def test_sandbox_failure(self, tmp_path: Path) -> None:
        installer, _, _, _ = _make_installer(tmp_path, sandbox_fail=True)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        result = await installer.install(payload, pkg, caller_id="user-1")

        assert result.success is False
        assert "SKILL_I004" in result.message


class TestRemove:
    @pytest.mark.asyncio
    async def test_remove_unregisters_skill(self, tmp_path: Path) -> None:
        installer, _, registry, _ = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        await installer.install(payload, pkg, caller_id="user-1")
        removed = await installer.remove("testskill")

        assert removed is True
        assert registry.get_by_id("testskill") is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_returns_false(self, tmp_path: Path) -> None:
        installer, _, _, _ = _make_installer(tmp_path)
        removed = await installer.remove("nonexistent")
        assert removed is False


class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_restores_version(self, tmp_path: Path) -> None:
        installer, _, registry, _ = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        await installer.install(payload, pkg, caller_id="user-1")

        result = await installer.rollback("testskill", "0.9.0")

        assert result.success is True
        assert result.version == "0.9.0"
        assert registry.get_by_id("testskill").version == "0.9.0"


class TestInstallerModule:
    def test_installer_has_no_forbidden_dependencies(self) -> None:
        """SkillInstaller must NOT depend on api/ or CLI modules."""
        import ast
        from pathlib import Path

        source = Path("core/skills/installer.py").read_text()
        tree = ast.parse(source)

        forbidden = {"api", "cli", "routes"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = set(node.module.split("."))
                overlap = parts & forbidden
                assert not overlap, f"Forbidden dependency: {node.module}"

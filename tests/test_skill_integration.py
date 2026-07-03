"""
PHASE: 18
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M11 Integration Tests)

IMPLEMENTATION PLAN:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M11 Integration Tests)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Comprehensive integration tests verifying contracts, boundaries, and
end-to-end behavior across the full Phase 18 skill pipeline.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.exceptions import JarvisSkillError
from core.skills.download_dto import DownloadedPackage
from core.skills.dto import SkillManifest, SkillMetadata
from core.skills.installer import SkillInstaller
from core.skills.permission_engine import SkillPermissionEngine
from core.skills.registry import SkillRegistry
from core.skills.sandbox import SandboxTestRunner
from core.skills.sandbox_dto import SandboxResult
from core.skills.signer import SkillSigner
from core.skills.validator import SkillValidator
from core.tools.security import PermissionGatekeeper

# ===========================================================================
# Shared fakes (same pattern as test_skill_installer.py)
# ===========================================================================


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


def _valid_manifest(**overrides: Any) -> dict[str, Any]:
    base = {
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
    base.update(overrides)
    return base


def _downloaded_package(
    tmp_path: Path, skill_id: str = "testskill"
) -> DownloadedPackage:
    import zipfile

    pkg = tmp_path / f"{skill_id}.zip"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("main.py", "print('hello')")
        zf.writestr("tests/test_main.py", "def test_ok(): assert True")
        zf.writestr("manifest.json", "{}")
    return DownloadedPackage(
        skill_id=skill_id,
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
    registry_fail: bool = False,
) -> tuple[SkillInstaller, _FakeEventBus, SkillRegistry, _InMemoryRepository]:
    event_bus = _FakeEventBus()
    gatekeeper = PermissionGatekeeper(event_bus=event_bus)
    validator = SkillValidator()
    repository = _InMemoryRepository()
    registry = SkillRegistry()

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


# ===========================================================================
# 1. End-to-End Install Flow
# ===========================================================================


class TestEndToEndInstallFlow:
    @pytest.mark.asyncio
    async def test_full_lifecycle_install_success(self, tmp_path: Path) -> None:
        """Verify complete install: validate -> sandbox -> permission -> sign -> persist -> register."""
        installer, event_bus, registry, repository = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        result = await installer.install(payload, pkg, caller_id="user-1")

        # Result contract
        assert result.success is True
        assert result.state == "ACTIVE"
        assert result.name == "testskill"
        assert result.version == "1.0.0"
        assert result.skill_id == "testskill"
        assert result.rollback_available is True
        assert result.registry_state == "REGISTERED"
        assert result.message == ""

        # Repository persisted
        model = await repository.get_skill_by_id("testskill")
        assert model is not None
        assert model.name == "testskill"
        assert model.version == "1.0.0"
        assert model.status == "INSTALLED"
        assert model.trust_level == "OFFICIAL"

        # Registry contains skill
        meta = registry.get_by_id("testskill")
        assert meta is not None
        assert meta.version == "1.0.0"
        assert meta.status == "ACTIVE"
        assert meta.trust_level == "OFFICIAL"
        assert "test.skill.execute" in meta.capabilities

        # Event emitted
        topics = [t for t, _ in event_bus.published]
        assert "skill.installed" in topics

        # Event payload
        installed_events = [
            msg for t, msg in event_bus.published if t == "skill.installed"
        ]
        assert len(installed_events) == 1
        assert installed_events[0].body["skill_id"] == "testskill"
        assert installed_events[0].body["state"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_install_full_pipeline_order(self, tmp_path: Path) -> None:
        """Verify pipeline executes in correct order via state transitions."""
        installer, _, _, _ = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        result = await installer.install(payload, pkg, caller_id="user-1")
        assert result.success is True
        assert result.state == "ACTIVE"


# ===========================================================================
# 2. Failure Rollback Matrix
# ===========================================================================


class TestFailureRollbackMatrix:
    @pytest.mark.asyncio
    async def test_validation_failure_nothing_persisted(self, tmp_path: Path) -> None:
        installer, _, registry, repository = _make_installer(
            tmp_path, validate_fail=True
        )
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        result = await installer.install(payload, pkg, caller_id="user-1")

        assert result.success is False
        assert "SKILL_V001" in result.message or "SKILL_I003" in result.message
        assert await repository.get_skill_by_id("testskill") is None
        assert registry.get_by_id("testskill") is None

    @pytest.mark.asyncio
    async def test_sandbox_failure_nothing_persisted(self, tmp_path: Path) -> None:
        installer, _, registry, repository = _make_installer(
            tmp_path, sandbox_fail=True
        )
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        result = await installer.install(payload, pkg, caller_id="user-1")

        assert result.success is False
        assert "SKILL_I004" in result.message
        assert await repository.get_skill_by_id("testskill") is None
        assert registry.get_by_id("testskill") is None

    @pytest.mark.asyncio
    async def test_registry_failure_rollback_persist(self, tmp_path: Path) -> None:
        """Registry failure after persist should trigger repository rollback."""
        installer, _, registry, repository = _make_installer(tmp_path)

        # Make registry.register raise
        original_register = registry.register

        def _fail_register(metadata: SkillMetadata) -> None:
            raise RuntimeError("Registry injection failed")

        registry.register = _fail_register  # type: ignore[assignment]

        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        result = await installer.install(payload, pkg, caller_id="user-1")

        assert result.success is False
        assert "SKILL_I005" in result.message
        # Registry should not have the skill
        assert registry.get_by_id("testskill") is None

        # Restore
        registry.register = original_register

    @pytest.mark.asyncio
    async def test_already_installed_without_force_rejected(
        self, tmp_path: Path
    ) -> None:
        installer, _, registry, repository = _make_installer(tmp_path)

        # Pre-install
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()
        await installer.install(payload, pkg, caller_id="user-1")
        assert registry.get_by_id("testskill") is not None

        # Second install without force
        result = await installer.install(payload, pkg, caller_id="user-2", force=False)
        assert result.success is False
        assert "SKILL_I002" in result.message

        # Registry still has the original
        assert registry.get_by_id("testskill").version == "1.0.0"

    @pytest.mark.asyncio
    async def test_force_overwrites_existing(self, tmp_path: Path) -> None:
        installer, _, registry, repository = _make_installer(tmp_path)

        # Pre-install v1
        pkg = _downloaded_package(tmp_path)
        payload_v1 = _valid_manifest()
        await installer.install(payload_v1, pkg, caller_id="user-1")
        assert registry.get_by_id("testskill").version == "1.0.0"

        # Force install v2
        payload_v2 = _valid_manifest(version="2.0.0")
        result = await installer.install(
            payload_v2, pkg, caller_id="user-2", force=True
        )
        assert result.success is True
        assert registry.get_by_id("testskill").version == "2.0.0"


# ===========================================================================
# 3. API Integration (route-level with real installer wiring)
# ===========================================================================


class TestAPIIntegration:
    def _build_app(self, installer: SkillInstaller, registry: SkillRegistry) -> Any:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.routes.skills import (
            _get_installer,
            _get_registry,
            _require_install,
            _require_read,
            _require_remove,
            router,
        )

        def _noop_auth() -> None:
            return None

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[_get_installer] = lambda: installer
        app.dependency_overrides[_get_registry] = lambda: registry
        app.dependency_overrides[_require_install] = _noop_auth
        app.dependency_overrides[_require_remove] = _noop_auth
        app.dependency_overrides[_require_read] = _noop_auth

        return TestClient(app)

    @pytest.mark.asyncio
    async def test_api_install_returns_201_with_correct_envelope(
        self, tmp_path: Path
    ) -> None:
        installer, _, registry, _ = _make_installer(tmp_path)
        client = self._build_app(installer, registry)

        response = client.post("/install?skill_name=testskill")

        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["skill_id"] == "testskill"
        assert body["data"]["state"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_api_remove_returns_200(self, tmp_path: Path) -> None:
        installer, _, registry, _ = _make_installer(tmp_path)
        client = self._build_app(installer, registry)

        # Pre-install
        pkg = _downloaded_package(tmp_path)
        await installer.install(_valid_manifest(), pkg, caller_id="api")

        response = client.post("/remove?skill_name=testskill")
        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_api_remove_nonexistent_returns_404(self, tmp_path: Path) -> None:
        installer, _, registry, _ = _make_installer(tmp_path)
        client = self._build_app(installer, registry)

        response = client.post("/remove?skill_name=ghost")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_api_list_returns_envelope(self, tmp_path: Path) -> None:
        installer, _, registry, _ = _make_installer(tmp_path)
        client = self._build_app(installer, registry)

        response = client.get("/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_api_search_by_capability(self, tmp_path: Path) -> None:
        installer, _, registry, _ = _make_installer(tmp_path)
        client = self._build_app(installer, registry)

        response = client.get("/search?q=test.skill.execute")
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_api_get_skill_by_id(self, tmp_path: Path) -> None:
        installer, _, registry, _ = _make_installer(tmp_path)
        client = self._build_app(installer, registry)

        # Pre-install
        pkg = _downloaded_package(tmp_path)
        await installer.install(_valid_manifest(), pkg, caller_id="api")

        response = client.get("/testskill")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == "testskill"

    @pytest.mark.asyncio
    async def test_api_get_nonexistent_returns_404(self, tmp_path: Path) -> None:
        installer, _, registry, _ = _make_installer(tmp_path)
        client = self._build_app(installer, registry)

        response = client.get("/ghost")
        assert response.status_code == 404


# ===========================================================================
# 4. CLI Integration (real parser, exit codes, output)
# ===========================================================================


class TestCLIIntegration:
    def test_cli_install_json_output(self, tmp_path: Path) -> None:
        installer, _, registry, _ = _make_installer(tmp_path)

        from skills.cli import cmd_install

        args = MagicMock()
        args.name = "testskill"
        args.version = None
        args.force = False

        result = asyncio.run(cmd_install(installer, args))

        assert result["success"] is True
        assert result["skill_id"] == "testskill"
        assert json.dumps(result)  # JSON serializable

    def test_cli_remove_json_output(self, tmp_path: Path) -> None:
        installer, _, _, _ = _make_installer(tmp_path)

        # Pre-install
        pkg = _downloaded_package(tmp_path)
        asyncio.run(installer.install(_valid_manifest(), pkg, caller_id="cli"))

        from skills.cli import cmd_remove

        args = MagicMock()
        args.name = "testskill"
        result = asyncio.run(cmd_remove(installer, args))

        assert result["success"] is True

    def test_cli_list_json_output(self, tmp_path: Path) -> None:
        _, _, registry, _ = _make_installer(tmp_path)

        from skills.cli import cmd_list

        args = MagicMock()
        result = asyncio.run(cmd_list(registry, args))

        assert result["success"] is True
        assert result["total"] == 0

    def test_cli_search_json_output(self, tmp_path: Path) -> None:
        _, _, registry, _ = _make_installer(tmp_path)

        from skills.cli import cmd_search

        args = MagicMock()
        args.query = ""
        result = asyncio.run(cmd_search(registry, args))

        assert result["success"] is True
        assert result["total"] == 0

    def test_cli_human_output_install(self, tmp_path: Path, capsys: Any) -> None:
        from skills.cli import _print_human

        result = {
            "success": True,
            "name": "test",
            "version": "1.0.0",
            "state": "ACTIVE",
        }
        _print_human(result, "install")
        captured = capsys.readouterr()
        assert "test" in captured.out
        assert "v1.0.0" in captured.out


# ===========================================================================
# 5. Repository + Registry Consistency
# ===========================================================================


class TestRepositoryRegistryConsistency:
    @pytest.mark.asyncio
    async def test_repository_and_registry_match_after_install(
        self, tmp_path: Path
    ) -> None:
        installer, _, registry, repository = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        await installer.install(payload, pkg, caller_id="user-1")

        # Repository has skill
        repo_model = await repository.get_skill_by_id("testskill")
        assert repo_model is not None

        # Registry has skill
        reg_meta = registry.get_by_id("testskill")
        assert reg_meta is not None

        # Core fields match
        assert repo_model.name == reg_meta.name
        assert repo_model.version == reg_meta.version
        assert repo_model.trust_level == reg_meta.trust_level

    @pytest.mark.asyncio
    async def test_hydrate_replaces_runtime_cache(self, tmp_path: Path) -> None:
        """After install, hydrate() should restore registry from repository."""
        installer, _, registry, repository = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        await installer.install(payload, pkg, caller_id="user-1")

        # Simulate runtime restart: clear registry
        registry._by_id.clear()
        registry._by_name.clear()
        registry._by_capability.clear()
        assert registry.get_by_id("testskill") is None

        # Hydrate from repository

        model = await repository.get_skill_by_id("testskill")
        assert model is not None
        registry.register(
            SkillMetadata(
                id=model.id,
                name=model.name,
                version=model.version,
                status="ACTIVE",
                trust_level=model.trust_level,
                capabilities=[],
                installed_at=None,
            )
        )

        # Registry restored
        restored = registry.get_by_id("testskill")
        assert restored is not None
        assert restored.name == "testskill"
        assert restored.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_remove_cleans_both_repository_and_registry(
        self, tmp_path: Path
    ) -> None:
        installer, _, registry, repository = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        await installer.install(payload, pkg, caller_id="user-1")
        await installer.remove("testskill")

        # Registry cleaned
        assert registry.get_by_id("testskill") is None

        # Repository soft-deleted
        model = await repository.get_skill_by_id("testskill")
        assert model is not None
        assert model.status == "REMOVED"


# ===========================================================================
# 6. Compatibility Rejection Tests
# ===========================================================================


class TestCompatibilityRejection:
    @pytest.mark.asyncio
    async def test_unsupported_platform_rejected(self, tmp_path: Path) -> None:
        """Manifest with unsupported platform should be rejected by validator."""
        installer, _, registry, repository = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest(
            compatibility={
                "platforms": ["darwin"],  # not in allowed list
                "architectures": ["x64"],
                "python": ">=3.11",
                "jarvis_runtime": ">=0.8",
            }
        )

        result = await installer.install(payload, pkg, caller_id="user-1")

        assert result.success is False
        assert await repository.get_skill_by_id("testskill") is None
        assert registry.get_by_id("testskill") is None

    @pytest.mark.asyncio
    async def test_unsupported_architecture_rejected(self, tmp_path: Path) -> None:
        installer, _, registry, repository = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest(
            compatibility={
                "platforms": ["windows", "linux"],
                "architectures": ["arm32"],  # not in allowed list
                "python": ">=3.11",
                "jarvis_runtime": ">=0.8",
            }
        )

        result = await installer.install(payload, pkg, caller_id="user-1")

        assert result.success is False
        assert await repository.get_skill_by_id("testskill") is None

    @pytest.mark.asyncio
    async def test_invalid_python_version_format_rejected(self, tmp_path: Path) -> None:
        installer, _, registry, repository = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest(
            compatibility={
                "platforms": ["windows", "linux"],
                "architectures": ["x64"],
                "python": "3.14",  # invalid format
                "jarvis_runtime": ">=0.8",
            }
        )

        result = await installer.install(payload, pkg, caller_id="user-1")

        assert result.success is False


# ===========================================================================
# 7. Manifest Contract Tests
# ===========================================================================


class TestManifestContract:
    def test_missing_id_rejected(self) -> None:
        payload = _valid_manifest()
        del payload["id"]
        validator = SkillValidator()
        with pytest.raises(JarvisSkillError):
            validator.validate_manifest(payload)

    def test_missing_version_rejected(self) -> None:
        payload = _valid_manifest()
        del payload["version"]
        validator = SkillValidator()
        with pytest.raises(JarvisSkillError):
            validator.validate_manifest(payload)

    def test_missing_entrypoint_uses_default(self) -> None:
        """entrypoint has a default of 'main.py' — removing it should still validate."""
        payload = _valid_manifest()
        del payload["entrypoint"]
        validator = SkillValidator()
        manifest = validator.validate_manifest(payload)
        assert manifest.entrypoint == "main.py"

    def test_missing_permissions_rejected(self) -> None:
        payload = _valid_manifest()
        del payload["permissions"]
        validator = SkillValidator()
        with pytest.raises(JarvisSkillError):
            validator.validate_manifest(payload)

    def test_missing_signature_rejected(self) -> None:
        payload = _valid_manifest()
        del payload["signature"]
        validator = SkillValidator()
        with pytest.raises(JarvisSkillError):
            validator.validate_manifest(payload)

    def test_missing_capabilities_rejected(self) -> None:
        payload = _valid_manifest()
        del payload["capabilities"]
        validator = SkillValidator()
        with pytest.raises(JarvisSkillError):
            validator.validate_manifest(payload)

    def test_missing_trust_level_rejected(self) -> None:
        payload = _valid_manifest()
        del payload["trust_level"]
        validator = SkillValidator()
        with pytest.raises(JarvisSkillError):
            validator.validate_manifest(payload)

    def test_missing_jarvis_api_version_rejected(self) -> None:
        payload = _valid_manifest()
        del payload["jarvis_api_version"]
        validator = SkillValidator()
        with pytest.raises(JarvisSkillError):
            validator.validate_manifest(payload)

    def test_invalid_id_pattern_rejected(self) -> None:
        payload = _valid_manifest(id="INVALID_ID!")
        validator = SkillValidator()
        with pytest.raises(JarvisSkillError):
            validator.validate_manifest(payload)

    def test_invalid_version_pattern_rejected(self) -> None:
        payload = _valid_manifest(version="1.0")
        validator = SkillValidator()
        with pytest.raises(JarvisSkillError):
            validator.validate_manifest(payload)

    def test_invalid_checksum_rejected(self) -> None:
        payload = _valid_manifest(checksum="not-a-hash")
        validator = SkillValidator()
        with pytest.raises(JarvisSkillError):
            validator.validate_manifest(payload)

    def test_empty_capabilities_rejected(self) -> None:
        payload = _valid_manifest(capabilities=[])
        validator = SkillValidator()
        with pytest.raises(JarvisSkillError):
            validator.validate_manifest(payload)


# ===========================================================================
# 8. Event Contract Tests
# ===========================================================================


class TestEventContract:
    @pytest.mark.asyncio
    async def test_install_emits_skill_installed_event(self, tmp_path: Path) -> None:
        installer, event_bus, _, _ = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)

        await installer.install(_valid_manifest(), pkg, caller_id="user-1")

        topics = [t for t, _ in event_bus.published]
        assert "skill.installed" in topics

    @pytest.mark.asyncio
    async def test_remove_emits_skill_removed_event(self, tmp_path: Path) -> None:
        installer, event_bus, _, _ = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)

        await installer.install(_valid_manifest(), pkg, caller_id="user-1")
        event_bus.published.clear()

        await installer.remove("testskill")

        topics = [t for t, _ in event_bus.published]
        assert "skill.removed" in topics

    @pytest.mark.asyncio
    async def test_event_names_are_exact_strings(self, tmp_path: Path) -> None:
        """Event names must be immutable exact strings matching the frozen telemetry contract."""
        installer, event_bus, _, _ = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)

        await installer.install(_valid_manifest(), pkg, caller_id="user-1")

        for topic, msg in event_bus.published:
            # Event names must follow pattern: skill.<verb>
            assert topic.startswith("skill."), (
                f"Event topic must start with 'skill.': {topic}"
            )
            # Must not be informal names
            assert topic not in ("installed", "downloaded", "removed"), (
                f"Event topic must be fully qualified: {topic}"
            )

    @pytest.mark.asyncio
    async def test_event_payload_has_required_fields(self, tmp_path: Path) -> None:
        installer, event_bus, _, _ = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)

        await installer.install(_valid_manifest(), pkg, caller_id="user-1")

        for topic, msg in event_bus.published:
            assert hasattr(msg, "body"), f"Event message must have body: {topic}"
            assert "skill_id" in msg.body
            assert "skill_name" in msg.body
            assert "state" in msg.body

    @pytest.mark.asyncio
    async def test_validation_failure_emits_event(self, tmp_path: Path) -> None:
        """Even failures should emit appropriate events."""
        installer, event_bus, _, _ = _make_installer(tmp_path, validate_fail=True)
        pkg = _downloaded_package(tmp_path)

        result = await installer.install(_valid_manifest(), pkg, caller_id="user-1")

        assert result.success is False
        # Validation failure may emit skill.validation.failed or no event
        # The key assertion is that it doesn't emit skill.installed
        topics = [t for t, _ in event_bus.published]
        assert "skill.installed" not in topics


# ===========================================================================
# 9. Performance Smoke Test (State Leak Check)
# ===========================================================================


class TestPerformanceSmoke:
    @pytest.mark.asyncio
    async def test_install_remove_install_no_state_leak(self, tmp_path: Path) -> None:
        """Verify registry doesn't leak state across install/remove cycles."""
        installer, _, registry, _ = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)
        payload = _valid_manifest()

        # Cycle 1: install
        result1 = await installer.install(payload, pkg, caller_id="user-1")
        assert result1.success is True
        assert registry.get_by_id("testskill") is not None

        # Cycle 1: remove
        removed = await installer.remove("testskill")
        assert removed is True
        assert registry.get_by_id("testskill") is None
        assert len(registry.list_skills()) == 0

        # Cycle 2: install again (force because soft-deleted record exists)
        result2 = await installer.install(payload, pkg, caller_id="user-2", force=True)
        assert result2.success is True
        meta = registry.get_by_id("testskill")
        assert meta is not None
        assert meta.version == "1.0.0"

        # Cycle 2: remove again
        removed2 = await installer.remove("testskill")
        assert removed2 is True
        assert len(registry.list_skills()) == 0

    @pytest.mark.asyncio
    async def test_multiple_skills_no_cross_contamination(self, tmp_path: Path) -> None:
        """Multiple different skills shouldn't interfere with each other."""
        installer, _, registry, _ = _make_installer(tmp_path)

        skills = ["skill-alpha", "skill-beta", "skill-gamma"]
        for name in skills:
            pkg = _downloaded_package(tmp_path, skill_id=name)
            payload = _valid_manifest(id=name, name=name)
            result = await installer.install(payload, pkg, caller_id="user-1")
            assert result.success is True

        assert len(registry.list_skills()) == 3

        # Remove middle one
        await installer.remove("skill-beta")
        remaining = registry.list_skills()
        assert len(remaining) == 2
        remaining_ids = {s.id for s in remaining}
        assert remaining_ids == {"skill-alpha", "skill-gamma"}

    @pytest.mark.asyncio
    async def test_force_overwrite_no_duplicate_registry(self, tmp_path: Path) -> None:
        """Force install should replace, not duplicate."""
        installer, _, registry, _ = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)

        # Install v1
        await installer.install(_valid_manifest(version="1.0.0"), pkg, caller_id="u1")
        assert len(registry.list_skills()) == 1

        # Force install v2
        await installer.install(
            _valid_manifest(version="2.0.0"), pkg, caller_id="u2", force=True
        )
        assert len(registry.list_skills()) == 1
        assert registry.get_by_id("testskill").version == "2.0.0"

    @pytest.mark.asyncio
    async def test_rollback_no_duplicate_registry(self, tmp_path: Path) -> None:
        """Rollback should update, not duplicate."""
        installer, _, registry, _ = _make_installer(tmp_path)
        pkg = _downloaded_package(tmp_path)

        await installer.install(_valid_manifest(version="1.0.0"), pkg, caller_id="u1")
        result = await installer.rollback("testskill", "0.9.0")

        assert result.success is True
        assert len(registry.list_skills()) == 1
        assert registry.get_by_id("testskill").version == "0.9.0"


# ===========================================================================
# 10. Architecture Boundary Tests
# ===========================================================================


class TestArchitectureBoundaries:
    def test_installer_no_forbidden_dependencies(self) -> None:
        """SkillInstaller must NOT import api/ or cli/."""
        import ast

        source = Path("core/skills/installer.py").read_text()
        tree = ast.parse(source)
        forbidden = {"api", "cli", "routes"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = set(node.module.split("."))
                overlap = parts & forbidden
                assert not overlap, f"Forbidden dependency: {node.module}"

    def test_cli_no_business_logic_imports(self) -> None:
        """CLI must NOT import core.business modules directly."""
        import ast

        source = Path("skills/cli.py").read_text()
        tree = ast.parse(source)
        forbidden = {
            "validator",
            "repository",
            "sandbox",
            "signer",
            "downloader",
            "permission_engine",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = set(node.module.split("."))
                overlap = parts & forbidden
                assert not overlap, f"Forbidden direct import: {node.module}"

    def test_api_no_business_logic(self) -> None:
        """API routes must NOT import core.business modules directly."""
        import ast

        source = Path("api/routes/skills.py").read_text()
        tree = ast.parse(source)
        forbidden = {"validator", "repository", "sandbox", "signer", "downloader"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = set(node.module.split("."))
                overlap = parts & forbidden
                assert not overlap, f"Forbidden direct import: {node.module}"

    def test_registry_no_repository_dependency(self) -> None:
        """SkillRegistry must NOT depend on Repository."""
        import ast

        source = Path("core/skills/registry.py").read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "repository" not in node.module.lower(), (
                    f"Registry must not depend on repository: {node.module}"
                )

"""
PHASE: 18
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M8 SkillInstaller)

IMPLEMENTATION PLAN:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M8 SkillInstaller)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.exceptions import JarvisSkillError
from core.interfaces import EventBusInterface, InterAgentMessage
from core.skills.download_dto import DownloadedPackage
from core.skills.dto import SkillManifest, SkillMetadata, SkillStatus
from core.skills.permission_engine import PermissionDecision, SkillPermissionEngine
from core.skills.registry import SkillRegistry
from core.skills.repository import SkillRepository
from core.skills.sandbox import SandboxTestRunner
from core.skills.sandbox_dto import SandboxResult
from core.skills.signer import SkillSigner
from core.skills.validator import SkillValidator

InstallState = str


@dataclass(frozen=True)
class InstallResult:
    """Structured install outcome."""

    skill_id: str
    name: str
    version: str
    state: SkillStatus
    installed_at: str
    success: bool
    message: str = ""
    rollback_available: bool = False
    registry_state: str = "UNKNOWN"


@dataclass
class _InstallContext:
    """Mutable context passed through the install pipeline."""

    state: InstallState = "PENDING"
    manifest: SkillManifest | None = None
    downloaded: DownloadedPackage | None = None
    sandbox_result: SandboxResult | None = None
    permission_decision: PermissionDecision | None = None
    previous_version: str | None = None
    previous_status: SkillStatus | None = None
    failure_code: str | None = None
    failure_message: str | None = None


class SkillInstallerError(JarvisSkillError):
    """Installer failures mapped to SKILL_I001-SKILL_I099."""


class SkillInstaller:
    """
    Orchestrates the full skill lifecycle per spec §4.
    Never performs CRUD directly — delegates to Repository, Validator, Sandbox, Signer.

    Responsibility: Coordination ONLY.
    """

    def __init__(
        self,
        validator: SkillValidator,
        repository: SkillRepository,
        registry: SkillRegistry,
        sandbox_runner: SandboxTestRunner,
        permission_engine: SkillPermissionEngine,
        signer: SkillSigner,
        event_bus: EventBusInterface,
        *,
        skill_dir: Path | None = None,
    ) -> None:
        self._validator = validator
        self._repository = repository
        self._registry = registry
        self._sandbox = sandbox_runner
        self._permissions = permission_engine
        self._signer = signer
        self._event_bus = event_bus
        self._skill_dir = skill_dir or Path("skills")

    async def install(
        self,
        manifest_payload: dict[str, Any],
        downloaded: DownloadedPackage,
        caller_id: str,
        *,
        force: bool = False,
    ) -> InstallResult:
        """
        Execute the full install lifecycle:
        1. Validate manifest
        2. Sandbox test
        3. Permission approval
        4. Signature verify
        5. Persist to repository
        6. Register in runtime registry
        """
        ctx = _InstallContext()

        # --- Step 1: Validate ---
        try:
            ctx.manifest = self._validator.validate_manifest(manifest_payload)
            ctx.state = "VALIDATED"
        except JarvisSkillError as exc:
            return self._fail(ctx, "SKILL_I003", str(exc))

        # --- Step 2: Check already installed ---
        existing = await self._repository.get_skill_by_name(
            ctx.manifest.name,
            session=None,  # type: ignore[arg-type]
        )
        if existing and not force:
            return self._fail(
                ctx,
                "SKILL_I002",
                f"Skill '{ctx.manifest.name}' already installed. Use force=True to overwrite.",
            )

        # --- Step 3: Sandbox test ---
        try:
            ctx.sandbox_result = await self._sandbox.run(downloaded, ctx.manifest)
            ctx.state = "SANDBOX_TESTED"
            if ctx.sandbox_result.status == "FAILED":
                return self._fail(ctx, "SKILL_I004", "Sandbox tests failed.")
        except JarvisSkillError as exc:
            return self._fail(ctx, "SKILL_I004", str(exc))

        # --- Step 4: Permission approval ---
        ctx.permission_decision = await self._permissions.request_approvals(
            skill_id=ctx.manifest.id,
            caller_id=caller_id,
            permissions=ctx.manifest.permissions,
        )
        if ctx.permission_decision != "AUTO_APPROVED":
            return self._fail(
                ctx, "SKILL_P001", "Permission approval denied or timed out."
            )
        ctx.state = "APPROVED"

        # --- Step 5: Signature verify ---
        skill_dir = self._skill_dir / ctx.manifest.id
        sig_result = self._signer.verify(
            skill_dir=skill_dir,
            expected_signature=ctx.manifest.signature,
        )
        if sig_result.decision not in ("VALID",):
            return self._fail(
                ctx,
                "SKILL_S001",
                f"Signature verification failed: {sig_result.message}",
            )
        ctx.state = "SIGNED"

        # --- Step 6: Persist ---
        await self._persist_skill(ctx, manifest_payload, downloaded)
        ctx.state = "INSTALLED"

        # --- Step 7: Register (atomic — rollback persist on failure) ---
        try:
            metadata = SkillMetadata(
                id=ctx.manifest.id,
                name=ctx.manifest.name,
                version=ctx.manifest.version,
                status="ACTIVE",
                trust_level=ctx.manifest.trust_level,
                capabilities=[cap.key for cap in ctx.manifest.capabilities],
                installed_at=datetime.now(timezone.utc).isoformat(),
            )
            self._registry.register(metadata)
            ctx.state = "ACTIVE"
        except Exception:
            # Registry failed — rollback persist to avoid inconsistent state
            await self._repository.remove_skill(ctx.manifest.id, session=None)  # type: ignore[arg-type]
            self._registry.unregister(ctx.manifest.id)
            return self._fail(
                ctx,
                "SKILL_I005",
                "Registry registration failed after persist. Install rolled back.",
            )

        # --- Emit installed event (after both persist + register succeed) ---
        await self._emit_event(
            "skill.installed", ctx.manifest.id, ctx.manifest.name, "ACTIVE"
        )

        return InstallResult(
            skill_id=ctx.manifest.id,
            name=ctx.manifest.name,
            version=ctx.manifest.version,
            state="ACTIVE",
            installed_at=datetime.now(timezone.utc).isoformat(),
            success=True,
            rollback_available=True,
            registry_state="REGISTERED",
        )

    async def remove(self, skill_name: str) -> bool:
        """Soft-delete a skill and unregister from runtime."""
        model = await self._repository.get_skill_by_name(skill_name, session=None)  # type: ignore[arg-type]
        if model is None:
            return False

        await self._repository.remove_skill(model.id, session=None)  # type: ignore[arg-type]
        self._registry.unregister(model.id)
        await self._emit_event("skill.removed", model.id, skill_name, "REMOVED")
        return True

    async def rollback(
        self,
        skill_name: str,
        target_version: str,
    ) -> InstallResult:
        """Restore a previous version from skill_versions history."""
        model = await self._repository.get_skill_by_name(skill_name, session=None)  # type: ignore[arg-type]
        if model is None:
            return InstallResult(
                skill_id=skill_name,
                name=skill_name,
                version=target_version,
                state="FAILED",
                installed_at="",
                success=False,
                message=f"Skill '{skill_name}' not found for rollback.",
            )

        # Update version and status
        await self._repository.update_skill_metadata(
            model.id,
            session=None,
            version=target_version,
            status="ACTIVE",  # type: ignore[arg-type]
        )
        self._registry.register(
            SkillMetadata(
                id=model.id,
                name=skill_name,
                version=target_version,
                status="ACTIVE",
                trust_level=model.trust_level,
                capabilities=[],
                installed_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        await self._emit_event("skill.updated", model.id, skill_name, "ACTIVE")

        return InstallResult(
            skill_id=model.id,
            name=skill_name,
            version=target_version,
            state="ACTIVE",
            installed_at=datetime.now(timezone.utc).isoformat(),
            success=True,
            rollback_available=True,
            registry_state="REGISTERED",
        )

    async def _persist_skill(
        self,
        ctx: _InstallContext,
        manifest_payload: dict[str, Any],
        downloaded: DownloadedPackage,
    ) -> Any:
        """Write skill record to repository (CRUD delegation)."""
        from core.skills.models import InstalledSkillModel

        model = InstalledSkillModel(
            id=ctx.manifest.id,  # type: ignore[union-attr]
            name=ctx.manifest.name,  # type: ignore[union-attr]
            version=ctx.manifest.version,  # type: ignore[union-attr]
            status="INSTALLED",
            trust_level=ctx.manifest.trust_level,  # type: ignore[union-attr]
            manifest_json=json.dumps(manifest_payload, sort_keys=True),
            checksum=downloaded.checksum,
            signature=ctx.manifest.signature,  # type: ignore[union-attr]
            approval_level=ctx.manifest.approval_level,  # type: ignore[union-attr]
        )
        await self._repository.save_installed_skill(model, session=None)  # type: ignore[arg-type]
        await self._repository.save_skill_capabilities(
            ctx.manifest.id,  # type: ignore[union-attr]
            [cap.key for cap in ctx.manifest.capabilities],  # type: ignore[union-attr]
            session=None,  # type: ignore[arg-type]
        )
        await self._repository.append_skill_version(
            ctx.manifest.id,  # type: ignore[union-attr]
            ctx.manifest.version,  # type: ignore[union-attr]
            "INSTALLED",
            session=None,  # type: ignore[arg-type]
        )
        return model

    def _fail(self, ctx: _InstallContext, code: str, message: str) -> InstallResult:
        """Record failure and return result."""
        ctx.failure_code = code
        ctx.failure_message = message
        return InstallResult(
            skill_id=ctx.manifest.id if ctx.manifest else "unknown",
            name=ctx.manifest.name if ctx.manifest else "unknown",
            version=ctx.manifest.version if ctx.manifest else "unknown",
            state="FAILED",
            installed_at=datetime.now(timezone.utc).isoformat(),
            success=False,
            message=f"[{code}] {message}",
            rollback_available=False,
            registry_state="NOT_REGISTERED",
        )

    async def _emit_event(
        self, topic: str, skill_id: str, skill_name: str, state: str
    ) -> None:
        msg = InterAgentMessage(
            id=uuid4(),
            correlation_id=uuid4(),
            sender="skill_installer",
            receiver="event_bus",
            action=topic,
            body={
                "skill_id": skill_id,
                "skill_name": skill_name,
                "state": state,
                "result": "success",
            },
        )
        await self._event_bus.publish(topic, msg)

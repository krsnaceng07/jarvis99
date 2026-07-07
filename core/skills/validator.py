"""
PHASE: 41
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/103_PHASE_41_CAPABILITY_REGISTRY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/8e27d67d-09cc-4e93-9e3e-d5a4bb653dd9/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from core.exceptions import JarvisSkillError
from core.skills.dto import SkillManifest


class SkillValidationCode(StrEnum):
    """Frozen error code contract for skill validation outcomes."""

    INVALID_MANIFEST = "SKILL_INVALID_MANIFEST"
    INVALID_VERSION = "SKILL_INVALID_VERSION"
    INVALID_CAPABILITY = "SKILL_INVALID_CAPABILITY"
    INVALID_DEPENDENCY = "SKILL_INVALID_DEPENDENCY"
    INVALID_PERMISSION = "SKILL_INVALID_PERMISSION"
    INVALID_SIGNATURE_METADATA = "SKILL_INVALID_SIGNATURE_METADATA"
    INVALID_COMPATIBILITY = "SKILL_INVALID_COMPATIBILITY"


class SkillValidator:
    """Pure validator for skill manifests and related contracts (no side effects)."""

    _PERMISSION_ALLOWLIST = {
        "network",
        "file_read",
        "file_write",
        "browser",
        "cli",
        "filesystem",
        "clipboard",
        "shell",
        "desktop",
        "internet.access",
        "filesystem.write",
        "filesystem.read",
    }

    _SEMVER_CONSTRAINT_PREFIXES = (">=", "<=", ">", "<", "==")

    def validate_manifest(self, payload: dict[str, Any]) -> SkillManifest:
        """Validate payload against frozen manifest contract and return parsed model."""
        self._validate_signature_metadata(payload)
        self._validate_permissions(payload)
        self._validate_dependency_schema(payload)
        self._validate_compatibility(payload)
        self._validate_versions(payload)
        self._validate_capabilities(payload)

        try:
            return SkillManifest.model_validate(payload)
        except ValidationError as err:
            raise JarvisSkillError(
                code=SkillValidationCode.INVALID_MANIFEST.value,
                message="Skill manifest schema validation failed.",
                details={"errors": err.errors()},
            ) from err

    def _validate_signature_metadata(self, payload: dict[str, Any]) -> None:
        signature = payload.get("signature")
        if not isinstance(signature, str) or not signature.strip():
            raise JarvisSkillError(
                code=SkillValidationCode.INVALID_SIGNATURE_METADATA.value,
                message="Missing or empty signature metadata.",
            )

    def _validate_permissions(self, payload: dict[str, Any]) -> None:
        permissions = payload.get("permissions")
        if not isinstance(permissions, list) or not permissions:
            raise JarvisSkillError(
                code=SkillValidationCode.INVALID_PERMISSION.value,
                message="Permissions must be a non-empty list.",
            )

        invalid = [
            p
            for p in permissions
            if not isinstance(p, str) or p not in self._PERMISSION_ALLOWLIST
        ]
        if invalid:
            raise JarvisSkillError(
                code=SkillValidationCode.INVALID_PERMISSION.value,
                message="Unsupported permission values detected.",
                details={"invalid_permissions": invalid},
            )

    def _validate_dependency_schema(self, payload: dict[str, Any]) -> None:
        dependencies = payload.get("dependencies", [])
        if not isinstance(dependencies, list):
            raise JarvisSkillError(
                code=SkillValidationCode.INVALID_DEPENDENCY.value,
                message="Dependencies must be a list.",
            )

        for dep in dependencies:
            if not isinstance(dep, dict):
                raise JarvisSkillError(
                    code=SkillValidationCode.INVALID_DEPENDENCY.value,
                    message="Dependency entries must be objects.",
                )
            skill = dep.get("skill")
            version = dep.get("version")
            if not isinstance(skill, str) or not skill:
                raise JarvisSkillError(
                    code=SkillValidationCode.INVALID_DEPENDENCY.value,
                    message="Dependency skill must be a non-empty string.",
                )
            if not isinstance(version, str) or not version:
                raise JarvisSkillError(
                    code=SkillValidationCode.INVALID_DEPENDENCY.value,
                    message="Dependency version must be a non-empty string.",
                )

    def _validate_compatibility(self, payload: dict[str, Any]) -> None:
        compatibility = payload.get("compatibility")
        if not isinstance(compatibility, dict):
            raise JarvisSkillError(
                code=SkillValidationCode.INVALID_COMPATIBILITY.value,
                message="Compatibility matrix is required.",
            )

        required = {"platforms", "architectures", "python", "jarvis_runtime"}
        missing = [key for key in required if key not in compatibility]
        if missing:
            raise JarvisSkillError(
                code=SkillValidationCode.INVALID_COMPATIBILITY.value,
                message="Compatibility matrix is missing required keys.",
                details={"missing": missing},
            )

    def _validate_versions(self, payload: dict[str, Any]) -> None:
        for key in ("version", "jarvis_api_version", "min_runtime_version"):
            value = payload.get(key)
            if not isinstance(value, str) or not value:
                raise JarvisSkillError(
                    code=SkillValidationCode.INVALID_VERSION.value,
                    message=f"Missing required version field: {key}",
                )

        dependencies = payload.get("dependencies", [])
        for dep in dependencies:
            version = dep.get("version") if isinstance(dep, dict) else None
            if not isinstance(version, str):
                continue
            if (
                not version.startswith(self._SEMVER_CONSTRAINT_PREFIXES)
                and not version[0].isdigit()
            ):
                raise JarvisSkillError(
                    code=SkillValidationCode.INVALID_VERSION.value,
                    message="Dependency version constraint is invalid.",
                    details={"version": version},
                )

    def _validate_capabilities(self, payload: dict[str, Any]) -> None:
        capabilities = payload.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            raise JarvisSkillError(
                code=SkillValidationCode.INVALID_CAPABILITY.value,
                message="Capabilities must be a non-empty list.",
            )

"""Phase 18 M1 validator contract tests (pure, no I/O)."""

from typing import Any

import pytest

from core.exceptions import JarvisSkillError
from core.skills.validator import SkillValidationCode, SkillValidator


def _valid_manifest_payload() -> dict[str, Any]:
    return {
        "id": "youtube",
        "name": "YouTube Skill",
        "version": "1.2.0",
        "author": "jarvis-official",
        "description": "Search and download YouTube content.",
        "entrypoint": "main.py",
        "permissions": ["network", "file_write"],
        "dependencies": [{"skill": "browser", "version": ">=1.2.0"}],
        "signature": "signed_payload_v1_abcdefghijklmnopqrstuvwxyz",
        "checksum": "a" * 64,
        "jarvis_api_version": "0.8",
        "min_runtime_version": "0.8",
        "approval_level": "L2",
        "trust_level": "OFFICIAL",
        "capabilities": [{"key": "youtube.video.search"}],
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
            "network": True,
            "filesystem": "sandbox",
        },
        "isolation": "container",
    }


def test_validate_manifest_success() -> None:
    validator = SkillValidator()
    model = validator.validate_manifest(_valid_manifest_payload())
    assert model.id == "youtube"
    assert model.version == "1.2.0"


def test_invalid_signature_metadata_code() -> None:
    validator = SkillValidator()
    payload = _valid_manifest_payload()
    payload["signature"] = ""

    with pytest.raises(JarvisSkillError) as exc:
        validator.validate_manifest(payload)

    assert exc.value.code == SkillValidationCode.INVALID_SIGNATURE_METADATA.value


def test_invalid_permission_code() -> None:
    validator = SkillValidator()
    payload = _valid_manifest_payload()
    payload["permissions"] = ["root.access"]

    with pytest.raises(JarvisSkillError) as exc:
        validator.validate_manifest(payload)

    assert exc.value.code == SkillValidationCode.INVALID_PERMISSION.value


def test_invalid_dependency_code() -> None:
    validator = SkillValidator()
    payload = _valid_manifest_payload()
    payload["dependencies"] = [{"skill": "browser"}]

    with pytest.raises(JarvisSkillError) as exc:
        validator.validate_manifest(payload)

    assert exc.value.code == SkillValidationCode.INVALID_DEPENDENCY.value


def test_invalid_compatibility_code() -> None:
    validator = SkillValidator()
    payload = _valid_manifest_payload()
    payload["compatibility"] = {"platforms": ["windows"]}

    with pytest.raises(JarvisSkillError) as exc:
        validator.validate_manifest(payload)

    assert exc.value.code == SkillValidationCode.INVALID_COMPATIBILITY.value


def test_invalid_capability_code() -> None:
    validator = SkillValidator()
    payload = _valid_manifest_payload()
    payload["capabilities"] = []

    with pytest.raises(JarvisSkillError) as exc:
        validator.validate_manifest(payload)

    assert exc.value.code == SkillValidationCode.INVALID_CAPABILITY.value


def test_invalid_version_code() -> None:
    validator = SkillValidator()
    payload = _valid_manifest_payload()
    payload["dependencies"] = [{"skill": "browser", "version": "not-semver-constraint"}]

    with pytest.raises(JarvisSkillError) as exc:
        validator.validate_manifest(payload)

    assert exc.value.code == SkillValidationCode.INVALID_VERSION.value


def test_schema_failure_maps_to_invalid_manifest() -> None:
    validator = SkillValidator()
    payload = _valid_manifest_payload()
    payload["id"] = "BAD UPPERCASE ID"

    with pytest.raises(JarvisSkillError) as exc:
        validator.validate_manifest(payload)

    assert exc.value.code == SkillValidationCode.INVALID_MANIFEST.value

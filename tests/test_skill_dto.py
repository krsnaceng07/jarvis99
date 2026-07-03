"""Phase 18 M0 DTO contract tests."""

from typing import Any

import pytest
from pydantic import ValidationError

from core.skills.dto import (
    InstallSkillRequest,
    InstallSkillResponse,
    SearchSkillRequest,
    SearchSkillResponse,
    SkillCapability,
    SkillCompatibility,
    SkillDependency,
    SkillLimits,
    SkillManifest,
    SkillMetadata,
)


def _manifest_payload() -> dict[str, Any]:
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


def test_manifest_valid_payload() -> None:
    manifest = SkillManifest.model_validate(_manifest_payload())
    assert manifest.id == "youtube"
    assert manifest.trust_level == "OFFICIAL"
    assert manifest.capabilities[0].key == "youtube.video.search"


def test_manifest_rejects_bad_checksum() -> None:
    payload = _manifest_payload()
    payload["checksum"] = "not_sha256"
    with pytest.raises(ValidationError):
        SkillManifest.model_validate(payload)


def test_manifest_rejects_bad_capability_format() -> None:
    payload = _manifest_payload()
    payload["capabilities"] = [{"key": "youtube.search"}]
    with pytest.raises(ValidationError):
        SkillManifest.model_validate(payload)


def test_dependency_contract() -> None:
    dep = SkillDependency(skill="browser", version=">=1.2.0")
    assert dep.skill == "browser"
    assert dep.version == ">=1.2.0"


def test_limits_contract() -> None:
    limits = SkillLimits(memory="1GB", cpu="1.5", timeout=120, network=False)
    assert limits.filesystem == "sandbox"


def test_compatibility_contract() -> None:
    compat = SkillCompatibility(
        platforms=["windows"],
        architectures=["arm64"],
        python=">=3.11",
        jarvis_runtime=">=0.8",
    )
    assert compat.platforms == ["windows"]


def test_install_request_contract() -> None:
    req = InstallSkillRequest(skill_name="youtube", version="1.2.0")
    assert req.force is False


def test_install_response_contract() -> None:
    resp = InstallSkillResponse(
        skill_id="youtube",
        name="YouTube Skill",
        version="1.2.0",
        status="INSTALLED",
    )
    assert resp.installed is True


def test_search_request_contract() -> None:
    req = SearchSkillRequest(query="youtube", source="all", limit=10, offset=0)
    assert req.limit == 10


def test_search_response_contract() -> None:
    item = SkillMetadata(
        id="youtube",
        name="YouTube Skill",
        version="1.2.0",
        status="ACTIVE",
        trust_level="OFFICIAL",
        capabilities=["youtube.video.search"],
    )
    resp = SearchSkillResponse(results=[item], total=1)
    assert resp.total == 1
    assert resp.results[0].id == "youtube"


def test_skill_capability_contract() -> None:
    cap = SkillCapability(key="github.repo.clone")
    assert cap.key == "github.repo.clone"

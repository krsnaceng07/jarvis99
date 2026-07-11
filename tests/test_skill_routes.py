"""Phase 18 M9 API route contract tests."""

from __future__ import annotations

from typing import Any

import pytest
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
from core.skills.dto import SkillMetadata
from core.skills.installer import InstallResult

# ---------------------------------------------------------------------------
# Fake Registry
# ---------------------------------------------------------------------------


class _FakeRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillMetadata] = {}

    def get_by_id(self, skill_id: str) -> SkillMetadata | None:
        return self._skills.get(skill_id)

    def list_skills(self, *, active_only: bool = False) -> list[SkillMetadata]:
        return list(self._skills.values())

    def find_by_capability(self, capability: str) -> list[SkillMetadata]:
        return [s for s in self._skills.values() if capability in s.capabilities]

    def register(self, metadata: SkillMetadata) -> None:
        self._skills[metadata.id] = metadata


# ---------------------------------------------------------------------------
# Fake Installer
# ---------------------------------------------------------------------------


class _FakeInstaller:
    def __init__(self, registry: _FakeRegistry) -> None:
        self._registry = registry
        self._installed: list[str] = []

    async def install(
        self,
        manifest_payload: Any,
        downloaded: Any,
        caller_id: str,
        *,
        force: bool = False,
    ) -> InstallResult:
        name = manifest_payload.get("id", "unknown")
        self._installed.append(name)
        self._registry.register(
            SkillMetadata(
                id=name,
                name=name,
                version="1.0.0",
                status="ACTIVE",
                trust_level="COMMUNITY",
                capabilities=[f"{name}.execute"],
            )
        )
        return InstallResult(
            skill_id=name,
            name=name,
            version="1.0.0",
            state="ACTIVE",
            installed_at="2026-01-01T00:00:00Z",
            success=True,
            rollback_available=True,
            registry_state="REGISTERED",
        )

    async def remove(self, skill_name: str) -> bool:
        if skill_name in self._registry._skills:
            del self._registry._skills[skill_name]
            return True
        return False


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------


def _noop_auth() -> None:
    return None


@pytest.fixture()
def client() -> tuple[TestClient, _FakeRegistry, _FakeInstaller]:
    registry = _FakeRegistry()
    installer = _FakeInstaller(registry)

    app = FastAPI()
    # Phase 18 spec: routes are mounted under /api/v1/skills in production
    # (api/main.py:158). Mirror that prefix here so the route table resolves
    # cleanly; the empty-path list_skills route cannot be mounted with a bare
    # include_router (FastAPI rejects prefix+path both empty).
    app.include_router(router, prefix="/api/v1/skills")

    app.dependency_overrides[_get_installer] = lambda: installer
    app.dependency_overrides[_get_registry] = lambda: registry
    app.dependency_overrides[_require_install] = _noop_auth
    app.dependency_overrides[_require_remove] = _noop_auth
    app.dependency_overrides[_require_read] = _noop_auth

    return TestClient(app), registry, installer


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInstallEndpoint:
    def test_install_returns_201(self, client: tuple) -> None:
        http, _, _ = client
        response = http.post("/api/v1/skills/install?skill_name=testskill")
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["skill_id"] == "testskill"

    def test_install_delegates_to_installer(self, client: tuple) -> None:
        http, _, installer = client
        http.post("/api/v1/skills/install?skill_name=myskill")
        assert "myskill" in installer._installed


class TestRemoveEndpoint:
    def test_remove_returns_200(self, client: tuple) -> None:
        http, registry, _ = client
        registry.register(
            SkillMetadata(
                id="todelete",
                name="todelete",
                version="1.0.0",
                status="ACTIVE",
                trust_level="COMMUNITY",
                capabilities=[],
            )
        )
        response = http.post("/api/v1/skills/remove?skill_name=todelete")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_remove_nonexistent_returns_404(self, client: tuple) -> None:
        http, _, _ = client
        response = http.post("/api/v1/skills/remove?skill_name=ghost")
        assert response.status_code == 404


class TestListEndpoint:
    def test_list_returns_skills(self, client: tuple) -> None:
        http, registry, _ = client
        registry.register(
            SkillMetadata(
                id="s1",
                name="s1",
                version="1.0.0",
                status="ACTIVE",
                trust_level="OFFICIAL",
                capabilities=[],
            )
        )
        response = http.get("/api/v1/skills")
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 1

    def test_list_empty(self, client: tuple) -> None:
        http, _, _ = client
        response = http.get("/api/v1/skills")
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 0


class TestSearchEndpoint:
    def test_search_by_capability(self, client: tuple) -> None:
        http, registry, _ = client
        registry.register(
            SkillMetadata(
                id="yt",
                name="yt",
                version="1.0.0",
                status="ACTIVE",
                trust_level="OFFICIAL",
                capabilities=["youtube.video.search"],
            )
        )
        response = http.get("/api/v1/skills/search?q=youtube.video.search")
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 1

    def test_search_no_match(self, client: tuple) -> None:
        http, _, _ = client
        response = http.get("/api/v1/skills/search?q=nonexistent.cap")
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 0


class TestGetSkillEndpoint:
    def test_get_existing_skill(self, client: tuple) -> None:
        http, registry, _ = client
        registry.register(
            SkillMetadata(
                id="known",
                name="known",
                version="1.0.0",
                status="ACTIVE",
                trust_level="COMMUNITY",
                capabilities=[],
            )
        )
        response = http.get("/api/v1/skills/known")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == "known"

    def test_get_nonexistent_returns_404(self, client: tuple) -> None:
        http, _, _ = client
        response = http.get("/api/v1/skills/ghost")
        assert response.status_code == 404


class TestRoutesModule:
    def test_routes_have_no_business_logic(self) -> None:
        """Routes must not import core.business modules directly."""
        import ast
        from pathlib import Path

        source = Path("api/routes/skills.py").read_text()
        tree = ast.parse(source)

        forbidden = {"validator", "repository", "sandbox", "signer", "downloader"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = set(node.module.split("."))
                overlap = parts & forbidden
                assert not overlap, f"Forbidden direct import: {node.module}"

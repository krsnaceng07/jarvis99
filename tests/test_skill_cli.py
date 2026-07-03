"""Phase 18 M10 CLI smoke tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from skills.cli import (
    _print_human,
    cmd_install,
    cmd_list,
    cmd_remove,
    cmd_search,
)

# ---------------------------------------------------------------------------
# Fake Installer
# ---------------------------------------------------------------------------


class _FakeInstaller:
    def __init__(self) -> None:
        self._installed: list[str] = []

    async def install(
        self,
        manifest_payload: Any,
        downloaded: Any,
        caller_id: str,
        *,
        force: bool = False,
    ) -> Any:
        name = manifest_payload.get("id", "unknown")
        self._installed.append(name)
        result = MagicMock()
        result.success = True
        result.skill_id = name
        result.name = name
        result.version = manifest_payload.get("version", "1.0.0")
        result.state = "ACTIVE"
        result.message = ""
        result.rollback_available = True
        result.registry_state = "REGISTERED"
        return result

    async def remove(self, skill_name: str) -> bool:
        if skill_name in self._installed:
            self._installed.remove(skill_name)
            return True
        return False


# ---------------------------------------------------------------------------
# Fake Registry
# ---------------------------------------------------------------------------


class _FakeRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Any] = {}

    def register(self, metadata: Any) -> None:
        self._skills[metadata.id] = metadata

    def list_skills(self, *, active_only: bool = False) -> list[Any]:
        return list(self._skills.values())

    def find_by_capability(self, capability: str) -> list[Any]:
        return [
            s
            for s in self._skills.values()
            if capability in getattr(s, "capabilities", [])
        ]


def _make_skill_metadata(
    skill_id: str, name: str, caps: list[str] | None = None
) -> Any:
    """Create a mock SkillMetadata."""
    meta = MagicMock()
    meta.id = skill_id
    meta.name = name
    meta.version = "1.0.0"
    meta.status = "ACTIVE"
    meta.trust_level = "COMMUNITY"
    meta.capabilities = caps or [f"{name}.execute"]
    meta.model_dump.return_value = {
        "id": skill_id,
        "name": name,
        "version": "1.0.0",
        "status": "ACTIVE",
        "trust_level": "COMMUNITY",
        "capabilities": caps or [f"{name}.execute"],
    }
    return meta


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInstallCommand:
    @pytest.mark.asyncio
    async def test_install_returns_success(self) -> None:
        installer = _FakeInstaller()
        args = MagicMock(name="testskill", version=None, force=False)
        args.name = "testskill"
        args.version = None
        args.force = False
        result = await cmd_install(installer, args)
        assert result["success"] is True
        assert result["skill_id"] == "testskill"
        assert "testskill" in installer._installed

    @pytest.mark.asyncio
    async def test_install_with_version(self) -> None:
        installer = _FakeInstaller()
        args = MagicMock()
        args.name = "myskill"
        args.version = "2.0.0"
        args.force = False
        result = await cmd_install(installer, args)
        assert result["version"] == "2.0.0"


class TestRemoveCommand:
    @pytest.mark.asyncio
    async def test_remove_existing(self) -> None:
        installer = _FakeInstaller()
        installer._installed.append("todelete")
        args = MagicMock()
        args.name = "todelete"
        result = await cmd_remove(installer, args)
        assert result["success"] is True
        assert "todelete" not in installer._installed

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self) -> None:
        installer = _FakeInstaller()
        args = MagicMock()
        args.name = "ghost"
        result = await cmd_remove(installer, args)
        assert result["success"] is False
        assert "not found" in result["error"]


class TestListCommand:
    @pytest.mark.asyncio
    async def test_list_empty(self) -> None:
        registry = _FakeRegistry()
        args = MagicMock()
        result = await cmd_list(registry, args)
        assert result["success"] is True
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_list_with_skills(self) -> None:
        registry = _FakeRegistry()
        registry.register(_make_skill_metadata("s1", "skill1"))
        registry.register(_make_skill_metadata("s2", "skill2"))
        args = MagicMock()
        result = await cmd_list(registry, args)
        assert result["total"] == 2


class TestSearchCommand:
    @pytest.mark.asyncio
    async def test_search_by_capability(self) -> None:
        registry = _FakeRegistry()
        registry.register(
            _make_skill_metadata("yt", "youtube", ["youtube.video.search"])
        )
        args = MagicMock()
        args.query = "youtube.video.search"
        result = await cmd_search(registry, args)
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_search_no_match(self) -> None:
        registry = _FakeRegistry()
        args = MagicMock()
        args.query = "nonexistent.cap"
        result = await cmd_search(registry, args)
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_search_empty_query_lists_all(self) -> None:
        registry = _FakeRegistry()
        registry.register(_make_skill_metadata("s1", "skill1"))
        args = MagicMock()
        args.query = ""
        result = await cmd_search(registry, args)
        assert result["total"] == 1


class TestPrintHuman:
    def test_print_install_success(self, capsys: Any) -> None:
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

    def test_print_list_empty(self, capsys: Any) -> None:
        result = {"success": True, "total": 0, "skills": []}
        _print_human(result, "list")
        captured = capsys.readouterr()
        assert "No skills installed" in captured.out

    def test_print_search_no_match(self, capsys: Any) -> None:
        result = {"success": True, "total": 0, "results": []}
        _print_human(result, "search")
        captured = capsys.readouterr()
        assert "No matching skills" in captured.out

    def test_print_error(self, capsys: Any) -> None:
        result = {"success": False, "error": "Something went wrong"}
        _print_human(result, "install")
        captured = capsys.readouterr()
        assert "Something went wrong" in captured.out


class TestCLIModule:
    def test_cli_has_no_forbidden_dependencies(self) -> None:
        """CLI must not import core.business modules directly."""
        import ast
        from pathlib import Path

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

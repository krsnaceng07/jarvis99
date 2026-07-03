"""Phase 18 M3 registry tests (runtime discovery only)."""

import importlib

from core.skills.dto import SkillMetadata
from core.skills.registry import SkillRegistry


def _metadata(
    skill_id: str,
    name: str,
    *,
    status: str = "ACTIVE",
    capabilities: list[str] | None = None,
    version: str = "1.0.0",
) -> SkillMetadata:
    return SkillMetadata(
        id=skill_id,
        name=name,
        version=version,
        status=status,  # type: ignore[arg-type]
        trust_level="OFFICIAL",
        capabilities=capabilities or [f"{skill_id}.resource.action"],
    )


def test_register_and_lookup_by_id_and_name() -> None:
    registry = SkillRegistry()
    entry = _metadata("youtube", "YouTube Skill")
    registry.register(entry)

    assert registry.get_by_id("youtube") == entry
    assert registry.get_by_name("YouTube Skill") == entry


def test_find_by_capability_is_capability_first() -> None:
    registry = SkillRegistry()
    youtube = _metadata(
        "youtube",
        "YouTube Skill",
        capabilities=["youtube.video.search", "youtube.video.download"],
    )
    github = _metadata(
        "github",
        "GitHub Skill",
        capabilities=["github.repo.clone"],
    )
    registry.register(youtube)
    registry.register(github)

    matches = registry.find_by_capability("youtube.video.search")
    assert len(matches) == 1
    assert matches[0].id == "youtube"


def test_unregister_removes_all_indexes() -> None:
    registry = SkillRegistry()
    entry = _metadata("slack", "Slack Skill", capabilities=["slack.message.send"])
    registry.register(entry)

    removed = registry.unregister("slack")
    assert removed is True
    assert registry.get_by_id("slack") is None
    assert registry.get_by_name("Slack Skill") is None
    assert registry.find_by_capability("slack.message.send") == []


def test_list_active_filters_non_active_statuses() -> None:
    registry = SkillRegistry()
    registry.register(_metadata("a", "Alpha", status="ACTIVE"))
    registry.register(_metadata("b", "Beta", status="REMOVED"))
    registry.register(_metadata("c", "Gamma", status="INSTALLED"))

    active = registry.list_active()
    active_ids = {item.id for item in active}
    assert active_ids == {"a", "c"}


def test_select_version_returns_registered_version() -> None:
    registry = SkillRegistry()
    registry.register(_metadata("docker", "Docker Skill", version="2.3.1"))

    assert registry.select_version("docker") == "2.3.1"
    assert registry.select_version("missing") is None


def test_hydrate_replaces_runtime_cache() -> None:
    registry = SkillRegistry()
    registry.register(_metadata("old", "Old Skill"))

    registry.hydrate(
        [
            _metadata("youtube", "YouTube Skill"),
            _metadata("notion", "Notion Skill"),
        ]
    )

    assert registry.get_by_id("old") is None
    assert registry.get_by_id("youtube") is not None
    assert registry.get_by_id("notion") is not None
    metadata = registry.get_metadata()
    assert metadata.total_skills == 2
    assert metadata.active_skills == 2


def test_registry_has_no_repository_dependency() -> None:
    module = importlib.import_module("core.skills.registry")
    module_path = module.__file__
    assert module_path is not None
    assert "SkillRepository" not in open(module_path, encoding="utf-8").read()

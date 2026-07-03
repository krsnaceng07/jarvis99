"""
PHASE: 18
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M3 Registry)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from pydantic import BaseModel, Field

from core.skills.dto import SkillMetadata, SkillStatus

_ACTIVE_STATUSES: frozenset[SkillStatus] = frozenset(
    {"ACTIVE", "INSTALLED", "REGISTERED"}
)


class SkillRegistryMetadata(BaseModel):
    """Runtime registry snapshot metadata (in-memory only)."""

    total_skills: int = Field(ge=0)
    active_skills: int = Field(ge=0)
    capability_index_size: int = Field(ge=0)
    indexed_capabilities: list[str] = Field(default_factory=list)


class SkillRegistry:
    """In-memory runtime registry for installed skill discovery."""

    def __init__(self) -> None:
        self._by_id: dict[str, SkillMetadata] = {}
        self._by_name: dict[str, str] = {}
        self._by_capability: dict[str, list[str]] = {}

    def register(self, metadata: SkillMetadata) -> None:
        """Register or replace a skill entry in runtime indexes."""
        self.unregister(metadata.id)
        self._by_id[metadata.id] = metadata
        self._by_name[metadata.name] = metadata.id
        for capability in metadata.capabilities:
            self._by_capability.setdefault(capability, []).append(metadata.id)

    def unregister(self, skill_id: str) -> bool:
        """Remove a skill from all runtime indexes."""
        metadata = self._by_id.pop(skill_id, None)
        if metadata is None:
            return False

        self._by_name.pop(metadata.name, None)
        for capability in metadata.capabilities:
            skill_ids = self._by_capability.get(capability, [])
            if skill_id in skill_ids:
                skill_ids.remove(skill_id)
            if not skill_ids:
                self._by_capability.pop(capability, None)
        return True

    def get_by_id(self, skill_id: str) -> SkillMetadata | None:
        """Lookup registered skill by stable ID."""
        return self._by_id.get(skill_id)

    def get_by_name(self, name: str) -> SkillMetadata | None:
        """Lookup registered skill by unique name."""
        skill_id = self._by_name.get(name)
        if skill_id is None:
            return None
        return self._by_id.get(skill_id)

    def find_by_capability(self, capability: str) -> list[SkillMetadata]:
        """Capability-first discovery for planner/runtime resolution."""
        skill_ids = self._by_capability.get(capability, [])
        return [
            self._by_id[skill_id] for skill_id in skill_ids if skill_id in self._by_id
        ]

    def list_skills(self, *, active_only: bool = False) -> list[SkillMetadata]:
        """List all registered skills, optionally filtered to active states."""
        entries = list(self._by_id.values())
        if not active_only:
            return entries
        return [entry for entry in entries if entry.status in _ACTIVE_STATUSES]

    def list_active(self) -> list[SkillMetadata]:
        """List skills currently considered active in runtime cache."""
        return self.list_skills(active_only=True)

    def select_version(self, skill_id: str) -> str | None:
        """Return the currently registered version for a skill ID."""
        metadata = self.get_by_id(skill_id)
        if metadata is None:
            return None
        return metadata.version

    def hydrate(self, entries: list[SkillMetadata]) -> None:
        """Replace runtime cache from externally loaded metadata (no persistence)."""
        self.clear()
        for entry in entries:
            self.register(entry)

    def clear(self) -> None:
        """Clear all in-memory registry indexes."""
        self._by_id.clear()
        self._by_name.clear()
        self._by_capability.clear()

    def get_metadata(self) -> SkillRegistryMetadata:
        """Return registry snapshot metadata for observability."""
        return SkillRegistryMetadata(
            total_skills=len(self._by_id),
            active_skills=len(self.list_active()),
            capability_index_size=len(self._by_capability),
            indexed_capabilities=sorted(self._by_capability.keys()),
        )

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

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CapabilityDetail(BaseModel):
    """Detailed metadata for a discoverable capability."""
    key: str = Field(
        pattern=r"^[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+$",
        min_length=3,
        max_length=120,
    )
    skill_id: str = Field(pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=300)
    permissions: List[str] = Field(default_factory=list)


class CapabilityRegistry:
    """Decouples dynamic capabilities from hardcoded tool lists by routing them via namespaced keys."""

    def __init__(self) -> None:
        """Initialize CapabilityRegistry."""
        self._capabilities: Dict[str, CapabilityDetail] = {}

    def register_capability(self, capability: CapabilityDetail) -> None:
        """Register a single capability mapping."""
        self._capabilities[capability.key] = capability

    def unregister_capability(self, key: str) -> bool:
        """Remove a capability registration."""
        if key in self._capabilities:
            del self._capabilities[key]
            return True
        return False

    def get_capability(self, key: str) -> Optional[CapabilityDetail]:
        """Lookup a capability mapping."""
        return self._capabilities.get(key)

    def search_capabilities(self, query: str) -> List[CapabilityDetail]:
        """Search capabilities by name key or description substring."""
        query_lower = query.lower()
        results = []
        for cap in self._capabilities.values():
            if (query_lower in cap.key.lower()) or (
                cap.description and query_lower in cap.description.lower()
            ):
                results.append(cap)
        return results

    def list_all(self) -> List[CapabilityDetail]:
        """List all currently registered capabilities."""
        return list(self._capabilities.values())

    def register_from_manifest(self, skill_id: str, manifest: Any) -> None:
        """Helper to register all capabilities from a skill manifest object or dict."""
        capabilities = getattr(manifest, "capabilities", [])
        permissions = getattr(manifest, "permissions", [])
        for cap in capabilities:
            key = getattr(cap, "key", None)
            if not key:
                if isinstance(cap, dict):
                    key = cap.get("key")
                    desc = cap.get("description")
                else:
                    key = str(cap)
                    desc = None
            else:
                desc = getattr(cap, "description", None)

            if key:
                self.register_capability(
                    CapabilityDetail(
                        key=key,
                        skill_id=skill_id,
                        description=desc,
                        permissions=permissions,
                    )
                )

"""JARVIS OS - Tool Registry.

Scans, parses, and registers dynamic skill manifest files, enforcing version compatibility and cryptographic signature integrity.
"""

import json
import os
from typing import Dict, Optional

from core.exceptions import JarvisSkillError
from core.tools.base import SkillManifest
from core.tools.security import PermissionGatekeeper


class ToolRegistry:
    """Discovers and registers sandboxed dynamic tools from manifests, checking compatibility and signatures."""

    SYSTEM_API_VERSION = "1.0"

    def __init__(self, skills_dir: str) -> None:
        """Initialize ToolRegistry.

        Args:
            skills_dir: Paths to directories housing dynamic skills.
        """
        self.skills_dir = skills_dir
        self.skills: Dict[str, SkillManifest] = {}

    def load_skill_manifest(self, skill_name: str) -> SkillManifest:
        """Load, parse, and validate the manifest of a single skill.

        Args:
            skill_name: Folder name under the skills directory.

        Returns:
            The parsed SkillManifest model.

        Raises:
            JarvisSkillError: If the manifest is missing, invalid, incompatible, or signature check fails.
        """
        skill_path = os.path.join(self.skills_dir, skill_name)
        manifest_path = os.path.join(skill_path, "manifest.json")

        if not os.path.exists(manifest_path):
            raise JarvisSkillError(
                code="SKILL_005",
                message=f"Manifest file missing for skill '{skill_name}' at {manifest_path}",
            )

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as err:
            raise JarvisSkillError(
                code="SKILL_005",
                message=f"Failed to parse manifest JSON for skill '{skill_name}': {str(err)}",
            )

        # 1. Parse using SkillManifest Pydantic schema
        try:
            manifest = SkillManifest(**data)
        except Exception as err:
            raise JarvisSkillError(
                code="SKILL_005",
                message=f"Manifest validation failed for skill '{skill_name}': {str(err)}",
            )

        # 2. Verify API Version compatibility
        if manifest.jarvis_api_version != self.SYSTEM_API_VERSION:
            raise JarvisSkillError(
                code="SKILL_006",
                message=(
                    f"API version mismatch for skill '{skill_name}'. "
                    f"Required: {self.SYSTEM_API_VERSION}, Found: {manifest.jarvis_api_version}"
                ),
            )

        # 3. Cryptographic signature check
        if not PermissionGatekeeper.verify_signature(skill_path, manifest.signature):
            raise JarvisSkillError(
                code="SKILL_007",
                message=f"Cryptographic signature check failed for skill '{skill_name}'. Package corrupted or tampered.",
            )

        self.skills[manifest.name] = manifest
        return manifest

    def discover_skills(self) -> None:
        """Scan the skills directory and load all valid skill manifests."""
        if not os.path.isdir(self.skills_dir):
            return

        for entry in os.listdir(self.skills_dir):
            entry_path = os.path.join(self.skills_dir, entry)
            if os.path.isdir(entry_path):
                try:
                    self.load_skill_manifest(entry)
                except JarvisSkillError:
                    # Log warning and continue scanning other folders
                    pass

    def get_skill(self, name: str) -> Optional[SkillManifest]:
        """Retrieve a registered skill by name.

        Args:
            name: The registered skill name.

        Returns:
            The SkillManifest DTO if registered, None otherwise.
        """
        return self.skills.get(name)

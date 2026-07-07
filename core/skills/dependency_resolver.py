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

from typing import Dict, List, Set

from core.exceptions import JarvisSkillError
from core.skills.dto import SkillManifest


class SkillDependencyResolver:
    """Resolves transitive skill dependencies, validating SemVer constraints and cycles."""

    def __init__(self, available_skills: Dict[str, SkillManifest]) -> None:
        """Initialize resolver with available skill manifests dictionary."""
        self._available = {k.lower(): v for k, v in available_skills.items()}

    def resolve_dependencies(self, manifest: SkillManifest) -> List[SkillManifest]:
        """Recursively resolves skill dependencies and returns them in topological order."""
        resolved: List[SkillManifest] = []
        visiting: Set[str] = set()
        visited: Set[str] = set()

        def _dfs(node: SkillManifest) -> None:
            node_id = node.id.lower()
            if node_id in visiting:
                raise JarvisSkillError(
                    code="SKILL_V005",
                    message=f"Circular dependency detected containing skill '{node.id}'",
                )
            if node_id in visited:
                return

            visiting.add(node_id)

            for dep in node.dependencies:
                dep_name = dep.skill.lower()
                if dep_name not in self._available:
                    raise JarvisSkillError(
                        code="SKILL_V003",
                        message=f"Dependency '{dep.skill}' is not available in the registry.",
                    )
                dep_manifest = self._available[dep_name]
                self._validate_version_constraint(
                    dep.version, dep_manifest.version, dep.skill
                )
                _dfs(dep_manifest)

            visiting.remove(node_id)
            visited.add(node_id)
            if node_id != manifest.id.lower():
                resolved.append(node)

        _dfs(manifest)
        return resolved

    def _validate_version_constraint(
        self, constraint: str, version: str, skill_name: str
    ) -> None:
        """Validates that a version string satisfies a target SemVer constraint expression."""
        try:
            v_parts = [int(x) for x in version.split(".")]
        except ValueError:
            return

        clean_constraint = constraint.strip()
        op = ""
        version_str = ""
        for prefix in (">=", "<=", ">", "<", "=="):
            if clean_constraint.startswith(prefix):
                op = prefix
                version_str = clean_constraint[len(prefix) :].strip()
                break

        if not op:
            if clean_constraint and clean_constraint[0].isdigit():
                op = "=="
                version_str = clean_constraint
            else:
                return

        try:
            c_parts = [int(x) for x in version_str.split(".")]
        except ValueError:
            return

        while len(c_parts) < 3:
            c_parts.append(0)
        while len(v_parts) < 3:
            v_parts.append(0)

        v_tuple = (v_parts[0], v_parts[1], v_parts[2])
        c_tuple = (c_parts[0], c_parts[1], c_parts[2])

        satisfied = False
        if op == ">=":
            satisfied = v_tuple >= c_tuple
        elif op == "<=":
            satisfied = v_tuple <= c_tuple
        elif op == ">":
            satisfied = v_tuple > c_tuple
        elif op == "<":
            satisfied = v_tuple < c_tuple
        elif op == "==":
            satisfied = v_tuple == c_tuple

        if not satisfied:
            raise JarvisSkillError(
                code="SKILL_V004",
                message=(
                    f"Dependency '{skill_name}' version '{version}' does "
                    f"not satisfy constraint '{constraint}'"
                ),
            )

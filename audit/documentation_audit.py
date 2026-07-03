"""
PHASE: 16
STATUS: IMPLEMENTATION
SPECIFICATION:
    AGENTS.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import os
import re
from typing import List

from audit.base import Audit
from audit.report import AuditResult, AuditStatus


class DocumentationAudit(Audit):
    """Audit check for broken relative and absolute file links."""

    @property
    def name(self) -> str:
        return "documentation"

    @property
    def description(self) -> str:
        return "Scans markdown files for broken file:/// links and checks master index integrity"

    def _resolve_link_path(self, link: str, root_dir: str) -> str | None:
        """Resolve a file:/// link to an absolute filesystem path.

        Handles drive letter variations dynamically by mapping repository relative segments.
        """
        # Strip protocol
        path_part = link.replace("file:///", "")

        # Remove any trailing anchor/line fragments
        path_part = path_part.split("#")[0]

        # Standardize slashes
        path_part = path_part.replace("/", os.sep)

        # If it refers to the workspace (e.g., containing 'jarvis'), resolve relative to root_dir
        if "jarvis" in path_part.lower():
            # Find the path after the 'jarvis' folder
            parts = path_part.split(os.sep)
            try:
                idx = -1
                for i, p in enumerate(parts):
                    if "jarvis" in p.lower():
                        idx = i
                        break
                if idx != -1:
                    rel_parts = parts[idx + 1 :]
                    return os.path.join(root_dir, *rel_parts)
            except Exception:
                pass

        # Fallback to direct absolute path resolution
        if os.path.isabs(path_part):
            return path_part

        # Fallback to relative to root_dir
        return os.path.join(root_dir, path_part)

    def _check_markdown_links(self, root_dir: str) -> List[str]:
        """Check all markdown files in the workspace for broken links."""
        broken_links: List[str] = []
        md_pattern = re.compile(r"\[[^\]]*\]\((file:///[^\)]+)\)")

        for root, dirs, files in os.walk(root_dir):
            if (
                ".venv" in root
                or "venv" in root
                or ".git" in root
                or "node_modules" in root
            ):
                continue

            for file in files:
                if file.endswith(".md"):
                    file_path = os.path.join(root, file)
                    rel_file_path = os.path.relpath(file_path, root_dir)

                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                    except Exception as e:
                        broken_links.append(
                            f"{rel_file_path}: Failed to read file: {e}"
                        )
                        continue

                    # Search for markdown links using file:/// protocol
                    for match in md_pattern.finditer(content):
                        link_uri = match.group(1)
                        resolved_path = self._resolve_link_path(link_uri, root_dir)

                        if resolved_path:
                            # Verify existence of the resolved path on disk
                            if not os.path.exists(resolved_path):
                                broken_links.append(
                                    f"Broken link in '{rel_file_path}': '{link_uri}' "
                                    f"(resolved to '{os.path.relpath(resolved_path, root_dir)}')"
                                )
                        else:
                            broken_links.append(
                                f"Invalid link URI format in '{rel_file_path}': '{link_uri}'"
                            )

        return broken_links

    def _check_master_index(self, root_dir: str) -> List[str]:
        """Verify the integrity of docs/60_MASTER_INDEX.md."""
        violations: List[str] = []
        index_path = os.path.join(root_dir, "docs", "60_MASTER_INDEX.md")

        if not os.path.exists(index_path):
            violations.append("docs/60_MASTER_INDEX.md is missing from the workspace.")
            return violations

        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse all links of form [xx_xxxx.md](file:///...) inside the index file
        links = re.findall(r"\[([a-zA-Z0-9_\-\.]+?)\]\((file:///[^\)]+)\)", content)

        for name, link_uri in links:
            resolved_path = self._resolve_link_path(link_uri, root_dir)
            if resolved_path:
                if not os.path.exists(resolved_path):
                    violations.append(
                        f"Master Index references non-existent file: '{name}' at path '{link_uri}'"
                    )
            else:
                violations.append(f"Master Index has invalid link format: '{link_uri}'")

        return violations

    async def run(self) -> AuditResult:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        broken_links = self._check_markdown_links(root_dir)
        master_violations = self._check_master_index(root_dir)

        all_violations = broken_links + master_violations

        details = {
            "broken_markdown_links": broken_links,
            "master_index_violations": master_violations,
            "total_violations": len(all_violations),
        }

        if all_violations:
            return AuditResult(
                name=self.name,
                status=AuditStatus.WARNING,
                message=f"Documentation checks found {len(all_violations)} broken link(s) in legacy documents.",
                details=details,
                duration_seconds=0.0,
            )

        return AuditResult(
            name=self.name,
            status=AuditStatus.PASS,
            message="All documentation file links and master index entries are resolved.",
            details=details,
            duration_seconds=0.0,
        )

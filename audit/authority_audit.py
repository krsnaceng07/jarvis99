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

import hashlib
import os
import re
from typing import List

from audit.base import Audit
from audit.report import AuditResult, AuditStatus


class AuthorityAudit(Audit):
    """Audit check for authority ranking, disclaimers, specs, and hash matching."""

    @property
    def name(self) -> str:
        return "authority"

    @property
    def description(self) -> str:
        return "Checks AGENTS.md rankings, walkthrough disclaimers, specification headers, and SHA hashes"

    def _compute_sha256(self, file_path: str) -> str:
        """Compute SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest().lower()

    def _check_agents_md(self, root_dir: str) -> List[str]:
        """Verify AGENTS.md structure and ranks."""
        violations = []
        path = os.path.join(root_dir, "AGENTS.md")
        if not os.path.exists(path):
            violations.append("AGENTS.md is missing from the workspace root.")
            return violations

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. Check Authority Ranking header exists
        if "## 1. Authority Ranking" not in content:
            violations.append("AGENTS.md is missing '## 1. Authority Ranking' section.")

        # 2. Check Rank 1-7 exist uniquely in the ranking table
        for rank in range(1, 8):
            pattern = re.compile(rf"\|\s*{rank}\s*(?:\([a-zA-Z\s]+\))?\s*\|")
            if not pattern.search(content):
                violations.append(
                    f"AGENTS.md: Rank {rank} is missing or formatted incorrectly in the authority table."
                )

        return violations

    def _check_walkthroughs(self, root_dir: str) -> List[str]:
        """Verify walkthrough disclaimer warnings and spec SHA hash integrity."""
        violations = []

        # Find all walkthrough files in workspace (e.g. walkthrough.md or inside brain folders)
        walkthrough_files = []
        for root, _, files in os.walk(root_dir):
            if ".venv" in root or "venv" in root or ".git" in root:
                continue
            for file in files:
                if file.endswith("walkthrough.md"):
                    walkthrough_files.append(os.path.join(root, file))

        for wt_path in walkthrough_files:
            rel_path = os.path.relpath(wt_path, root_dir)
            with open(wt_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 1. Check disclaimer warnings
            for term in ["NOT AUTHORITATIVE", "Specification wins", "AGENTS.md wins"]:
                if term not in content:
                    violations.append(
                        f"Walkthrough '{rel_path}' is missing disclaimer term: '{term}'"
                    )

            # 2. Validate spec SHA hash if declared in walkthrough
            sha_match = re.search(
                r"\*\s*\*\*Specification SHA256\*\*:\s*([0-9a-fA-F]{64})", content
            )
            spec_match = re.search(
                r"\*\s*\*\*Specification\*\*:\s*([^\s\r\n]+)", content
            )

            if sha_match and spec_match:
                declared_sha = sha_match.group(1).lower()
                spec_rel_path = spec_match.group(1).strip()
                # Clean links formatting if any (e.g. removing file:/// absolute paths or brackets)
                spec_rel_path = spec_rel_path.replace("file:///", "").replace("`", "")

                # Resolve spec path
                spec_abs_path = os.path.abspath(os.path.join(root_dir, spec_rel_path))
                if not os.path.exists(spec_abs_path):
                    # Check relative to doc root directly if relative path was absolute
                    spec_abs_path = os.path.join(
                        root_dir, "docs", os.path.basename(spec_rel_path)
                    )

                if os.path.exists(spec_abs_path):
                    actual_sha = self._compute_sha256(spec_abs_path)
                    if actual_sha != declared_sha:
                        violations.append(
                            f"Walkthrough '{rel_path}' declares SHA256 '{declared_sha}' for spec '{spec_rel_path}', "
                            f"but actual SHA256 is '{actual_sha}'."
                        )
                else:
                    violations.append(
                        f"Walkthrough '{rel_path}' references specification file '{spec_rel_path}' which does not exist."
                    )

        return violations

    def _check_specification_headers(self, root_dir: str) -> List[str]:
        """Verify that all specifications in docs/ have valid STATUS status headers."""
        violations: List[str] = []
        docs_dir = os.path.join(root_dir, "docs")
        if not os.path.exists(docs_dir):
            return violations

        for file in os.listdir(docs_dir):
            if file.endswith("_SPECIFICATION.md"):
                file_path = os.path.join(docs_dir, file)
                rel_path = os.path.relpath(file_path, root_dir)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Check for ## Status section
                if "## Status" not in content and "## STATUS" not in content:
                    violations.append(
                        f"Specification '{rel_path}' is missing a '## Status' header."
                    )
                    continue

                # Check if STATUS is declared as Frozen, Draft, Approved, etc.
                status_pattern = re.compile(
                    r"STATUS[\*\_:]*\s*(?:Frozen|FROZEN|Draft|DRAFT|Approved|APPROVED|Archived|Deprecated|Superseded)",
                    re.IGNORECASE,
                )
                if not status_pattern.search(content):
                    violations.append(
                        f"Specification '{rel_path}' has a Status section but no valid status state (e.g. Frozen, Draft)."
                    )

        return violations

    async def run(self) -> AuditResult:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        agents_violations = self._check_agents_md(root_dir)
        walkthrough_violations = self._check_walkthroughs(root_dir)
        spec_violations = self._check_specification_headers(root_dir)

        all_violations = agents_violations + walkthrough_violations + spec_violations

        details = {
            "agents_md_violations": agents_violations,
            "walkthrough_violations": walkthrough_violations,
            "specification_violations": spec_violations,
            "total_violations_found": len(all_violations),
        }

        if all_violations:
            return AuditResult(
                name=self.name,
                status=AuditStatus.FAIL,
                message=f"Authority and governance checks failed with {len(all_violations)} violations.",
                details=details,
                duration_seconds=0.0,
            )

        return AuditResult(
            name=self.name,
            status=AuditStatus.PASS,
            message="AGENTS.md rankings, walkthrough disclaimers, specification headers, and SHA hashes are valid.",
            details=details,
            duration_seconds=0.0,
        )

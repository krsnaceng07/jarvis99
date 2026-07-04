"""
PHASE: 19
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/phases/phase19/m5_5_engineering_governance_freeze.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional


def check_governance(
    manifest_file: Path, gov_dir: Path, pmg_dir: Optional[Path] = None
) -> int:
    """Validate all governance criteria. Returns exit code 0 or 1."""
    errors = []

    # 1. Read manifest and verify mandatory files
    if not manifest_file.is_file():
        errors.append(f"Manifest file not found: {manifest_file}")
    else:
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            required = manifest.get("required_documents", [])
            for doc_rel in required:
                # The paths in manifest are relative to repo root (e.g. docs/governance/pre_milestone_gate.md)
                # Let's resolve against the parent of docs/ (which is the repo root)
                repo_root = gov_dir.parent.parent
                doc_path = repo_root / doc_rel
                if not doc_path.is_file():
                    errors.append(f"Mandatory document missing: {doc_rel}")
        except Exception as e:
            errors.append(f"Failed to read manifest: {e}")

    # 2. Dynamic scan of docs/governance/*.md for STATUS: FROZEN
    if gov_dir.is_dir():
        status_pattern = re.compile(r"status\s*:\s*.*frozen", re.IGNORECASE)
        for md_file in gov_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                # Search for status line
                if not status_pattern.search(content):
                    errors.append(
                        f"Document status is not FROZEN: docs/governance/{md_file.name}"
                    )
            except Exception as e:
                errors.append(f"Failed to read document {md_file.name}: {e}")
    else:
        errors.append(f"Governance directory not found: {gov_dir}")

    # 3. Check Pre-Milestone Gates (PMGs) if directory is specified and exists
    if pmg_dir and pmg_dir.is_dir():
        hard_stops = {
            "2.1": "Spec frozen",
            "2.2": "ADR exists",
            "2.3": "Public interface frozen",
            "2.4": "DTO frozen",
            "2.7": "Architecture reviewed",
            "2.11": "Security review",
        }
        for pmg_file in pmg_dir.glob("*.md"):
            try:
                content = pmg_file.read_text(encoding="utf-8")
                for code, label in hard_stops.items():
                    pattern = re.compile(
                        rf"{re.escape(code)}\s+.*?\s+(YES|NO|N/A)", re.IGNORECASE
                    )
                    match = pattern.search(content)
                    if match:
                        val = match.group(1).upper()
                        if val != "YES":
                            errors.append(
                                f"PMG {pmg_file.name}: Hard-STOP checkpoint {code} ({label}) evaluates to '{val}' (must be YES)"
                            )
                    else:
                        errors.append(
                            f"PMG {pmg_file.name}: Mandatory checkpoint {code} ({label}) not found"
                        )
            except Exception as e:
                errors.append(f"Failed to read PMG file {pmg_file.name}: {e}")

    if errors:
        print("Governance validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("Governance validation PASSED. All documents and PMG gates verified.")
    return 0


def main() -> None:
    repo_dir = Path(__file__).resolve().parent.parent
    gov_dir = repo_dir / "docs" / "governance"
    manifest_file = gov_dir / "governance_manifest.json"
    pmg_dir = gov_dir / "pmg"

    # Quick help
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python scripts/governance_check.py")
        sys.exit(0)

    exit_code = check_governance(manifest_file, gov_dir, pmg_dir)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

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
from pathlib import Path

from scripts.governance_check import check_governance


def test_check_governance_valid(tmp_path: Path) -> None:
    repo_dir = tmp_path
    gov_dir = repo_dir / "docs" / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)

    # Create manifest
    manifest_file = gov_dir / "governance_manifest.json"
    manifest_data: dict[str, list[str]] = {
        "required_documents": ["docs/governance/doc_a.md", "docs/governance/doc_b.md"]
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    # Create doc_a and doc_b with frozen status
    doc_a = gov_dir / "doc_a.md"
    doc_a.write_text(
        """
# Doc A
**Status:** ✅ FROZEN — 2026-07-03
""",
        encoding="utf-8",
    )

    doc_b = gov_dir / "doc_b.md"
    doc_b.write_text(
        """
# Doc B
**Status:** FROZEN
""",
        encoding="utf-8",
    )

    # Create a PMG file
    pmg_dir = gov_dir / "pmg"
    pmg_dir.mkdir(parents=True, exist_ok=True)
    pmg_file = pmg_dir / "PMG-M5.5.3.md"
    pmg_file.write_text(
        """
PRE-MILESTONE GATE — M5.5.3
[x] 2.1  Spec frozen?                       YES
[x] 2.2  ADR exists?                        YES
[x] 2.3  Public interface frozen?           YES
[x] 2.4  DTO frozen?                        YES
[x] 2.7  Architecture reviewed?             YES
[x] 2.11 Security review?                   YES
""",
        encoding="utf-8",
    )

    exit_code = check_governance(manifest_file, gov_dir, pmg_dir)
    assert exit_code == 0


def test_check_governance_missing_mandatory(tmp_path: Path) -> None:
    repo_dir = tmp_path
    gov_dir = repo_dir / "docs" / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)

    # Create manifest with doc_b, but only doc_a exists
    manifest_file = gov_dir / "governance_manifest.json"
    manifest_data: dict[str, list[str]] = {
        "required_documents": ["docs/governance/doc_a.md", "docs/governance/doc_b.md"]
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    doc_a = gov_dir / "doc_a.md"
    doc_a.write_text(
        """
# Doc A
**Status:** ✅ FROZEN
""",
        encoding="utf-8",
    )

    exit_code = check_governance(manifest_file, gov_dir, None)
    assert exit_code == 1


def test_check_governance_not_frozen(tmp_path: Path) -> None:
    repo_dir = tmp_path
    gov_dir = repo_dir / "docs" / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)

    manifest_file = gov_dir / "governance_manifest.json"
    manifest_data: dict[str, list[str]] = {
        "required_documents": ["docs/governance/doc_a.md"]
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    # Status is DRAFT
    doc_a = gov_dir / "doc_a.md"
    doc_a.write_text(
        """
# Doc A
**Status:** DRAFT
""",
        encoding="utf-8",
    )

    exit_code = check_governance(manifest_file, gov_dir, None)
    assert exit_code == 1


def test_check_governance_pmg_hard_stop_failed(tmp_path: Path) -> None:
    repo_dir = tmp_path
    gov_dir = repo_dir / "docs" / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)

    manifest_file = gov_dir / "governance_manifest.json"
    manifest_data: dict[str, list[str]] = {"required_documents": []}
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    # PMG has NO for Spec frozen
    pmg_dir = gov_dir / "pmg"
    pmg_dir.mkdir(parents=True, exist_ok=True)
    pmg_file = pmg_dir / "PMG-M5.5.3.md"
    pmg_file.write_text(
        """
PRE-MILESTONE GATE — M5.5.3
[ ] 2.1  Spec frozen?                       NO
[ ] 2.2  ADR exists?                        YES
[ ] 2.3  Public interface frozen?           YES
[ ] 2.4  DTO frozen?                        YES
[ ] 2.7  Architecture reviewed?             YES
[ ] 2.11 Security review?                   YES
""",
        encoding="utf-8",
    )

    exit_code = check_governance(manifest_file, gov_dir, pmg_dir)
    assert exit_code == 1

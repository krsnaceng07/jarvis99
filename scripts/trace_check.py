"""
PHASE: 19
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/governance/decision_traceability.md

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
from typing import Dict, List


def parse_trace_table(content: str) -> List[Dict[str, str]]:
    """Parse markdown table rows from TRACE.md."""
    rows: List[Dict[str, str]] = []
    lines = content.strip().splitlines()
    for line in lines:
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue

        parts = [p.strip() for p in line.split("|")]
        # Remove empty items from leading/trailing splits
        if len(parts) < 10:
            continue
        parts = parts[1:-1]

        trace_id = parts[0]
        # Skip header or separator
        if trace_id == "TRACE-ID" or trace_id.startswith("---"):
            continue

        rows.append(
            {
                "trace_id": trace_id,
                "rfc": parts[1],
                "adr": parts[2],
                "spec": parts[3],
                "code": parts[4],
                "test": parts[5],
                "doc": parts[6],
                "status": parts[7],
            }
        )
    return rows


def extract_base_path(raw_path: str) -> str:
    """Extract the base file path from a cell, stripping line numbers, section signs, or pytest separators."""
    p = raw_path.strip()
    p = p.split("::")[0]
    p = p.split(":")[0]
    p = p.split(" ")[0]
    p = p.split("§")[0]
    return p.strip()


def check_traceability(trace_file: Path, cache_file: Path, repo_dir: Path) -> int:
    """Validate the traceability matrix and write JSON cache. Returns exit code 0 or 1."""
    if not trace_file.is_file():
        print(
            f"ERROR: Traceability matrix file not found: {trace_file}", file=sys.stderr
        )
        return 1

    try:
        content = trace_file.read_text(encoding="utf-8")
    except Exception as e:
        print(f"ERROR: Failed to read TRACE.md: {e}", file=sys.stderr)
        return 1

    rows = parse_trace_table(content)
    if not rows:
        print("WARNING: No traces found in TRACE.md.", file=sys.stderr)

    trace_id_pattern = re.compile(r"^TRACE-\d+-(?:M\d+(?:\.\d+)*|global)-\d+$")
    errors = []

    for idx, row in enumerate(rows):
        trace_id = row["trace_id"]
        status = row["status"]

        # 1. Validate TRACE-ID format
        if not trace_id_pattern.match(trace_id):
            errors.append(f"Row {idx + 1}: Invalid TRACE-ID format: '{trace_id}'")
            continue

        # 2. Check path existences on disk for populated fields
        mandatory_fields = ["spec", "code", "test", "doc"]
        missing_mandatory = False

        for field in mandatory_fields:
            val = row[field]
            if val in ("", "—", "-"):
                missing_mandatory = True
                continue

            # Resolve file path
            base_p = extract_base_path(val)
            full_p = repo_dir / base_p
            if not full_p.exists():
                errors.append(
                    f"Row {idx + 1} ({trace_id}): File does not exist for {field}: '{base_p}'"
                )

        # 3. Check status consistency
        if missing_mandatory:
            if status == "CLOSED":
                errors.append(
                    f"Row {idx + 1} ({trace_id}): Status mismatch. Closed trace must have Spec, Code, Test, and Doc populated."
                )
        else:
            if status == "OPEN":
                errors.append(
                    f"Row {idx + 1} ({trace_id}): Status mismatch. Trace with all mandatory fields populated must be CLOSED."
                )

        if status not in ("OPEN", "CLOSED", "SUPERSEDED"):
            errors.append(f"Row {idx + 1} ({trace_id}): Invalid status: '{status}'")

    if errors:
        print("Traceability validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    # Write trace JSON cache
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"Traceability validation PASSED. Cache saved to: {cache_file}")
    except Exception as e:
        print(f"ERROR: Failed to write trace.json cache: {e}", file=sys.stderr)
        return 1

    return 0


def main() -> None:
    repo_dir = Path(__file__).resolve().parent.parent
    trace_file = repo_dir / "docs" / "decisions" / "TRACE.md"
    cache_file = repo_dir / "docs" / "decisions" / "trace.json"

    # Quick help
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python scripts/trace_check.py")
        sys.exit(0)

    exit_code = check_traceability(trace_file, cache_file, repo_dir)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

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
from pathlib import Path

from scripts.trace_check import check_traceability, parse_trace_table


def test_parse_trace_table_valid() -> None:
    content = """
# Decisions Traceability Matrix

| TRACE-ID | RFC | ADR | Spec | Code | Test | Doc | Status |
|---|---|---|---|---|---|---|---|
| TRACE-19-M6-001 | RFC-01 | ADR-05 | docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md | api/main.py:42 | tests/test_smoke.py::test_smoke | docs/00_PROJECT_CONSTITUTION.md §3.1 | CLOSED |
| TRACE-19-M6-002 | — | — | docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md | api/main.py | — | — | OPEN |
"""
    rows = parse_trace_table(content)
    assert len(rows) == 2
    assert rows[0]["trace_id"] == "TRACE-19-M6-001"
    assert rows[0]["rfc"] == "RFC-01"
    assert rows[0]["code"] == "api/main.py:42"
    assert rows[0]["status"] == "CLOSED"

    assert rows[1]["trace_id"] == "TRACE-19-M6-002"
    assert rows[1]["rfc"] == "—"
    assert rows[1]["status"] == "OPEN"


def test_check_traceability_valid(tmp_path: Path) -> None:
    repo_dir = tmp_path
    trace_file = repo_dir / "docs" / "decisions" / "TRACE.md"
    trace_file.parent.mkdir(parents=True, exist_ok=True)

    # Create files linked in the trace
    code_file = repo_dir / "api" / "main.py"
    code_file.parent.mkdir(parents=True, exist_ok=True)
    code_file.touch()

    test_file = repo_dir / "tests" / "test_smoke.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.touch()

    doc_file = repo_dir / "docs" / "00_PROJECT_CONSTITUTION.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.touch()

    spec_file = (
        repo_dir / "docs" / "80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md"
    )
    spec_file.parent.mkdir(parents=True, exist_ok=True)
    spec_file.touch()

    content = """
| TRACE-ID | RFC | ADR | Spec | Code | Test | Doc | Status |
|---|---|---|---|---|---|---|---|
| TRACE-19-M6-001 | RFC-01 | ADR-05 | docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md | api/main.py:42 | tests/test_smoke.py::test_smoke | docs/00_PROJECT_CONSTITUTION.md §3.1 | CLOSED |
| TRACE-19-M6-002 | — | — | docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md | api/main.py | — | — | OPEN |
"""
    trace_file.write_text(content, encoding="utf-8")

    cache_file = repo_dir / "docs" / "decisions" / "trace.json"
    exit_code = check_traceability(trace_file, cache_file, repo_dir)
    assert exit_code == 0

    assert cache_file.exists()
    with open(cache_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 2
    assert data[0]["trace_id"] == "TRACE-19-M6-001"
    assert data[0]["status"] == "CLOSED"


def test_check_traceability_invalid_format(tmp_path: Path) -> None:
    repo_dir = tmp_path
    trace_file = repo_dir / "docs" / "decisions" / "TRACE.md"
    trace_file.parent.mkdir(parents=True, exist_ok=True)

    spec_file = (
        repo_dir / "docs" / "80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md"
    )
    spec_file.parent.mkdir(parents=True, exist_ok=True)
    spec_file.touch()

    code_file = repo_dir / "api" / "main.py"
    code_file.parent.mkdir(parents=True, exist_ok=True)
    code_file.touch()

    test_file = repo_dir / "tests" / "test_smoke.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.touch()

    doc_file = repo_dir / "docs" / "00_PROJECT_CONSTITUTION.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.touch()

    # Invalid TRACE-ID format
    content = """
| TRACE-ID | RFC | ADR | Spec | Code | Test | Doc | Status |
|---|---|---|---|---|---|---|---|
| INVALID-TRACE-01 | RFC-01 | ADR-05 | docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md | api/main.py | tests/test_smoke.py | docs/00_PROJECT_CONSTITUTION.md | CLOSED |
"""
    trace_file.write_text(content, encoding="utf-8")
    cache_file = repo_dir / "docs" / "decisions" / "trace.json"
    exit_code = check_traceability(trace_file, cache_file, repo_dir)
    assert exit_code == 1


def test_check_traceability_missing_file(tmp_path: Path) -> None:
    repo_dir = tmp_path
    trace_file = repo_dir / "docs" / "decisions" / "TRACE.md"
    trace_file.parent.mkdir(parents=True, exist_ok=True)

    spec_file = (
        repo_dir / "docs" / "80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md"
    )
    spec_file.parent.mkdir(parents=True, exist_ok=True)
    spec_file.touch()

    # Points to non-existent code file api/missing_file.py
    content = """
| TRACE-ID | RFC | ADR | Spec | Code | Test | Doc | Status |
|---|---|---|---|---|---|---|---|
| TRACE-19-M6-001 | RFC-01 | ADR-05 | docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md | api/missing_file.py | tests/test_smoke.py | docs/00_PROJECT_CONSTITUTION.md | CLOSED |
"""
    trace_file.write_text(content, encoding="utf-8")
    cache_file = repo_dir / "docs" / "decisions" / "trace.json"
    exit_code = check_traceability(trace_file, cache_file, repo_dir)
    assert exit_code == 1


def test_check_traceability_status_mismatch_open(tmp_path: Path) -> None:
    repo_dir = tmp_path
    trace_file = repo_dir / "docs" / "decisions" / "TRACE.md"
    trace_file.parent.mkdir(parents=True, exist_ok=True)

    spec_file = (
        repo_dir / "docs" / "80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md"
    )
    spec_file.parent.mkdir(parents=True, exist_ok=True)
    spec_file.touch()

    code_file = repo_dir / "api" / "main.py"
    code_file.parent.mkdir(parents=True, exist_ok=True)
    code_file.touch()

    test_file = repo_dir / "tests" / "test_smoke.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.touch()

    doc_file = repo_dir / "docs" / "00_PROJECT_CONSTITUTION.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.touch()

    # All links present but marked OPEN
    content = """
| TRACE-ID | RFC | ADR | Spec | Code | Test | Doc | Status |
|---|---|---|---|---|---|---|---|
| TRACE-19-M6-001 | RFC-01 | ADR-05 | docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md | api/main.py | tests/test_smoke.py | docs/00_PROJECT_CONSTITUTION.md | OPEN |
"""
    trace_file.write_text(content, encoding="utf-8")
    cache_file = repo_dir / "docs" / "decisions" / "trace.json"
    exit_code = check_traceability(trace_file, cache_file, repo_dir)
    assert exit_code == 1


def test_check_traceability_status_mismatch_closed(tmp_path: Path) -> None:
    repo_dir = tmp_path
    trace_file = repo_dir / "docs" / "decisions" / "TRACE.md"
    trace_file.parent.mkdir(parents=True, exist_ok=True)

    spec_file = (
        repo_dir / "docs" / "80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md"
    )
    spec_file.parent.mkdir(parents=True, exist_ok=True)
    spec_file.touch()

    code_file = repo_dir / "api" / "main.py"
    code_file.parent.mkdir(parents=True, exist_ok=True)
    code_file.touch()

    test_file = repo_dir / "tests" / "test_smoke.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.touch()

    # Missing doc link but marked CLOSED
    content = """
| TRACE-ID | RFC | ADR | Spec | Code | Test | Doc | Status |
|---|---|---|---|---|---|---|---|
| TRACE-19-M6-001 | RFC-01 | ADR-05 | docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md | api/main.py | tests/test_smoke.py | — | CLOSED |
"""
    trace_file.write_text(content, encoding="utf-8")
    cache_file = repo_dir / "docs" / "decisions" / "trace.json"
    exit_code = check_traceability(trace_file, cache_file, repo_dir)
    assert exit_code == 1

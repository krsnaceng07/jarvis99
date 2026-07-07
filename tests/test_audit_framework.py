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
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from audit.architecture_audit import ArchitectureAudit
from audit.authority_audit import AuthorityAudit
from audit.cli import main, run_audits
from audit.documentation_audit import DocumentationAudit
from audit.quality_audit import QualityAudit
from audit.report import AuditResult, AuditStatus
from audit.repository_audit import RepositoryAudit


@pytest.mark.asyncio
async def test_architecture_audit_mocked_failure() -> None:
    """Test that ArchitectureAudit correctly identifies layering violations and circular dependencies."""
    audit = ArchitectureAudit()

    # Mock ast parsing to simulate a layering violation (core imports api)
    with (
        patch.object(
            audit,
            "_get_python_files",
            return_value=[("/mock/core/brain.py", "core.brain")],
        ),
        patch.object(audit, "_parse_imports", return_value={"api.main"}),
    ):
        res = await audit.run()
        assert res.status == AuditStatus.FAIL
        assert "layer violation(s) detected" in res.message
        assert len(res.details["layer_violations"]) == 1

    # Mock dependency graph to simulate circular dependency
    with (
        patch.object(
            audit,
            "_get_python_files",
            return_value=[
                ("/mock/core/a.py", "core.a"),
                ("/mock/core/b.py", "core.b"),
            ],
        ),
        patch.object(
            audit,
            "_parse_imports",
            side_effect=lambda fp, mn: {"core.b"} if mn == "core.a" else {"core.a"},
        ),
    ):
        res = await audit.run()
        assert res.status == AuditStatus.FAIL
        assert "Circular dependency cycle detected" in res.message
        assert "core.a -> core.b -> core.a" in res.message


@pytest.mark.asyncio
async def test_authority_audit_mocked_failure() -> None:
    """Test that AuthorityAudit flags violations when AGENTS.md ranking is missing or wrong."""
    audit = AuthorityAudit()

    # Mock missing AGENTS.md
    with patch(
        "os.path.exists", side_effect=lambda p: False if "AGENTS.md" in p else True
    ):
        res = await audit.run()
        assert res.status == AuditStatus.FAIL
        assert "AGENTS.md is missing" in res.details["agents_md_violations"][0]


@pytest.mark.asyncio
async def test_documentation_audit_mocked_failure() -> None:
    """Test that DocumentationAudit identifies broken markdown file:/// links."""
    audit = DocumentationAudit()

    # Mock missing file link resolution
    with (
        patch.object(
            audit,
            "_check_markdown_links",
            return_value=["Broken link in 'docs/00_PROJECT_CONSTITUTION.md'"],
        ),
        patch.object(audit, "_check_master_index", return_value=[]),
    ):
        res = await audit.run()
        assert res.status == AuditStatus.WARNING
        assert "broken link(s)" in res.message


@pytest.mark.asyncio
async def test_repository_audit_mocked_header_failure() -> None:
    """Test that RepositoryAudit flags modified python files lacking standardized headers."""
    audit = RepositoryAudit()

    # Mock modified files list and check_header return
    with (
        patch.object(
            audit,
            "_get_modified_python_files",
            return_value={os.path.abspath("audit/cli.py")},
        ),
        patch.object(
            audit,
            "_check_header",
            return_value="Missing required header fields: PHASE:",
        ),
    ):
        res = await audit.run()
        assert res.status == AuditStatus.FAIL
        assert "Repository checks failed" in res.message
        assert len(res.details["header_violations"]) == 1


@pytest.mark.asyncio
async def test_quality_audit_mocked_failures() -> None:
    """Test that QualityAudit handles failures from Ruff, Mypy, and Pytest subprocesses."""
    audit = QualityAudit()

    # Mock subprocess failures
    mock_run = MagicMock()
    mock_run.returncode = 1
    mock_run.stdout = "Linting errors found"
    mock_run.stderr = ""

    with patch("subprocess.run", return_value=mock_run):
        res = await audit.run()
        assert res.status == AuditStatus.FAIL
        assert "Quality gates check failed" in res.message
        assert res.details["total_quality_issues"] > 0


@pytest.mark.asyncio
async def test_cli_run_audits_filtering() -> None:
    """Test running a specific audit check by name filters execution correctly."""
    report = await run_audits(
        selected_audit_name="architecture", verbose=False, quiet=True
    )
    assert len(report.results) == 1
    assert report.results[0].name == "architecture"


def test_documentation_audit_link_resolution() -> None:
    """Test link resolution logic in DocumentationAudit."""
    audit = DocumentationAudit()
    root = os.path.abspath("e:/jarvis")

    # Absolute link resolution
    res = audit._resolve_link_path("file:///e:/jarvis/docs/01_PROJECT_CHARTER.md", root)
    assert res is not None
    assert "01_PROJECT_CHARTER.md" in res

    # Relative link resolution
    res2 = audit._resolve_link_path("file:///docs/01_PROJECT_CHARTER.md", root)
    assert res2 is not None
    assert "01_PROJECT_CHARTER.md" in res2

    # Absolute path fallback
    res3 = audit._resolve_link_path("file:///c:/some/absolute/path.md", root)
    assert res3 is not None
    assert "some" in res3


@pytest.mark.asyncio
async def test_documentation_audit_full_flow() -> None:
    """Test full link checking execution of DocumentationAudit with mocked filesystem."""
    audit = DocumentationAudit()
    root = os.path.abspath("e:/jarvis")

    mock_md_content = (
        "This is a test link: [charter](file:///e:/jarvis/docs/missing.md)"
    )

    # Mock os.walk, open, and path checking
    with (
        patch("os.walk", return_value=[(os.path.join(root, "docs"), [], ["test.md"])]),
        patch("builtins.open", mock_open(read_data=mock_md_content)),
        patch("os.path.exists", side_effect=lambda p: False),
    ):
        res = await audit.run()
        assert res.status == AuditStatus.WARNING
        assert len(res.details["broken_markdown_links"]) > 0


@pytest.mark.asyncio
async def test_authority_audit_full_flow() -> None:
    """Test full authority audit run with mock contents for AGENTS.md and walkthrough.md."""
    audit = AuthorityAudit()
    _ = os.path.abspath("e:/jarvis")

    agents_content = (
        "# AGENTS.md\n## 1. Authority Ranking\n"
        "| Rank | Source |\n"
        "|---|---|\n"
        "| 1 | User |\n"
        "| 2 | AGENTS.md |\n"
        "| 3 | 60_MASTER_INDEX.md |\n"
        "| 4 | Phase Spec |\n"
        "| 5 | Implementation plan |\n"
        "| 6 | Code |\n"
        "| 7 | Walkthrough |\n"
    )
    walkthrough_content = (
        "WARNING\nNOT AUTHORITATIVE\nSpecification wins\nAGENTS.md wins"
    )

    def mock_exists(path: str) -> bool:
        if "AGENTS.md" in path or "walkthrough.md" in path:
            return True
        return False

    def mock_walk(dir_path: str) -> list:
        if "docs" in dir_path:
            return [(dir_path, [], ["75_PHASE_13_MASTER_SPECIFICATION.md"])]
        return [(dir_path, [], ["walkthrough.md"])]

    # Mock file reading
    def mock_file_open(path: str, *args, **kwargs):
        if "AGENTS.md" in path:
            return mock_open(read_data=agents_content)()
        elif "walkthrough" in path:
            return mock_open(read_data=walkthrough_content)()
        elif "SPECIFICATION" in path:
            return mock_open(read_data="## Status\nSTATUS: Frozen")()
        return mock_open(read_data="")()

    with (
        patch("os.path.exists", side_effect=mock_exists),
        patch("os.walk", side_effect=mock_walk),
        patch("builtins.open", side_effect=mock_file_open),
    ):
        res = await audit.run()
        assert res.status == AuditStatus.PASS


@pytest.mark.asyncio
async def test_repository_audit_naming_and_headers() -> None:
    """Test RepositoryAudit naming convention and header verification checks."""
    import audit.repository_audit as _ra_mod

    audit_obj = RepositoryAudit()
    # Mirror the exact root_dir logic from RepositoryAudit.run() so paths are
    # consistent across Windows and WSL/Linux environments.
    root = os.path.dirname(os.path.dirname(os.path.abspath(_ra_mod.__file__)))

    header_valid = '"""\nPHASE: 16\nSTATUS: IMPLEMENTATION\nSPECIFICATION:\nIMPLEMENTATION PLAN:\nAUTHORITATIVE:\nDO NOT CHANGE CONTRACTS HERE.\n"""'

    def mock_walk(dir_path: str) -> list:
        return [
            (os.path.join(root, "api"), [], ["camelCaseFile.py"]),
            (os.path.join(root, "core"), [], ["clean_file.py"]),
        ]

    with (
        patch("os.walk", side_effect=mock_walk),
        patch("os.path.exists", return_value=True),
        patch("os.path.getsize", return_value=500),
        patch("builtins.open", mock_open(read_data=header_valid)),
    ):
        res = await audit_obj.run()
        assert res.status == AuditStatus.FAIL
        assert len(res.details["naming_violations"]) > 0


def test_cli_main_entrypoint() -> None:
    """Test CLI main entrypoint arguments parsing and execution outputs."""
    mock_report = MagicMock()
    mock_report.overall_status = AuditStatus.PASS
    mock_report.results = []

    with (
        patch("sys.argv", ["cli.py", "--audit", "architecture", "--quiet"]),
        patch("sys.exit") as mock_exit,
        patch("audit.cli.run_audits") as _,
        patch("asyncio.run", return_value=mock_report),
    ):
        main()
        mock_exit.assert_called_once_with(0)


@pytest.mark.asyncio
async def test_run_audits_verbose() -> None:
    """Test run_audits with verbose and normal paths to exercise logging branches."""
    mock_res = AuditResult(
        name="test_audit",
        status=AuditStatus.PASS,
        message="Pass message",
        details={"info": "ok"},
        duration_seconds=0.1,
    )
    with (
        patch(
            "audit.architecture_audit.ArchitectureAudit.run",
            new_callable=AsyncMock,
            return_value=mock_res,
        ),
        patch(
            "audit.authority_audit.AuthorityAudit.run",
            new_callable=AsyncMock,
            return_value=mock_res,
        ),
        patch(
            "audit.documentation_audit.DocumentationAudit.run",
            new_callable=AsyncMock,
            return_value=mock_res,
        ),
        patch(
            "audit.quality_audit.QualityAudit.run",
            new_callable=AsyncMock,
            return_value=mock_res,
        ),
        patch(
            "audit.repository_audit.RepositoryAudit.run",
            new_callable=AsyncMock,
            return_value=mock_res,
        ),
    ):
        report = await run_audits(None, verbose=True, quiet=False)
        assert report.overall_status == AuditStatus.PASS

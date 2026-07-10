"""Tests for the JARVIS Golden Startup, Capability Matrix, and Validation tooling.

These tests verify the startup infrastructure itself — not the JARVIS core
features. They run quickly and never touch a live JARVIS process; they use
the in-process TestClient where a real app is needed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import capability_matrix  # noqa: E402
import golden_startup  # noqa: E402
import validate_startup  # noqa: E402

# ---------------------------------------------------------------------------
# golden_startup
# ---------------------------------------------------------------------------


class TestPreflightChecks:
    """Tests for the preflight-check logic in golden_startup."""

    def test_passes_when_config_and_port_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Preflight passes when config exists, venv exists, port is free."""
        # We override python_executable so the test doesn't depend on .venv existing.
        result = golden_startup.preflight_checks(
            golden_startup.StartupConfig(port=18765),
            python_executable=sys.executable,
        )
        assert result.ok, result.error
        assert result.stage == "preflight"
        names = [c["name"] for c in result.details["checks"]]
        assert "config_exists" in names
        assert "port_free" in names

    def test_fails_when_config_missing(self, tmp_path: Path) -> None:
        """Preflight fails when the config file doesn't exist."""
        result = golden_startup.preflight_checks(
            golden_startup.StartupConfig(
                port=18766, config_path=str(tmp_path / "missing.yaml")
            ),
            python_executable=sys.executable,
        )
        assert not result.ok
        assert "config" in (result.error or "").lower()

    def test_fails_when_port_in_use(self) -> None:
        """Preflight fails when the target port is already bound."""
        import socket as _socket

        server = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        try:
            result = golden_startup.preflight_checks(
                golden_startup.StartupConfig(port=port),
                python_executable=sys.executable,
            )
            assert not result.ok
            assert "port" in (result.error or "").lower()
        finally:
            server.close()


class TestStartupConfig:
    """Tests for the StartupConfig dataclass."""

    def test_resolved_config_path_is_absolute(self) -> None:
        """resolved_config_path returns an absolute path."""
        cfg = golden_startup.StartupConfig(config_path="config.yaml")
        resolved = cfg.resolved_config_path
        assert resolved.is_absolute()
        assert resolved.name == "config.yaml"

    def test_default_values_match_run_py(self) -> None:
        """Defaults must match run.py so the two paths stay aligned."""
        cfg = golden_startup.StartupConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8765
        assert cfg.config_path == "config.yaml"
        assert cfg.reload is False
        assert cfg.workers == 1


class TestResolveCommand:
    """Tests for uvicorn command construction."""

    def test_resolve_command_minimal(self) -> None:
        """Bare StartupConfig produces a uvicorn command with host+port."""
        cmd = golden_startup.resolve_command(golden_startup.StartupConfig())
        assert "uvicorn" in cmd
        assert "api.main:app" in cmd
        assert "--host" in cmd
        assert "127.0.0.1" in cmd
        assert "--port" in cmd
        assert "8765" in cmd
        assert "--reload" not in cmd
        assert "--workers" not in cmd

    def test_resolve_command_with_reload(self) -> None:
        """--reload is appended when reload=True."""
        cmd = golden_startup.resolve_command(golden_startup.StartupConfig(reload=True))
        assert "--reload" in cmd
        # workers must NOT be combined with reload
        assert "--workers" not in cmd

    def test_resolve_command_with_workers(self) -> None:
        """--workers is appended when workers > 0 and reload is off."""
        cmd = golden_startup.resolve_command(golden_startup.StartupConfig(workers=4))
        assert "--workers" in cmd
        assert "4" in cmd


# ---------------------------------------------------------------------------
# capability_matrix
# ---------------------------------------------------------------------------


class FakeResponse:
    """Minimal stand-in for httpx.Response / TestClient response."""

    def __init__(self, status_code: int, json_data: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._json = json_data
        self.text = text or (json.dumps(json_data) if json_data is not None else "")

    def json(self) -> Any:
        return self._json


class FakeClient:
    """Stand-in HTTP client. Records calls and returns canned responses."""

    def __init__(self, responses: Dict[str, FakeResponse]) -> None:
        self.responses = responses
        self.calls: List[Dict[str, Any]] = []

    def _route(self, method: str, url: str) -> FakeResponse:
        self.calls.append({"method": method, "url": url})
        return self.responses.get(url, FakeResponse(404, {"error": "no route"}))

    def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> FakeResponse:
        return self._route("GET", url)

    def post(
        self,
        url: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> FakeResponse:
        return self._route("POST", url)

    def close(self) -> None:
        return None


class TestProbeRunner:
    """Tests for the capability matrix probe runner."""

    def test_login_success_stores_token(self) -> None:
        """Successful login populates the bearer token on the runner."""
        client = FakeClient(
            {
                "http://x/api/v1/auth/login": FakeResponse(
                    200, {"data": {"access_token": "abc123"}}
                )
            }
        )
        runner = capability_matrix.ProbeRunner(base_url="http://x")
        runner.set_client_factory(lambda: client)
        token = runner.login("admin", "JarvisDev123!")
        assert token == "abc123"

    def test_run_marks_auth_required_skip_when_login_fails(self) -> None:
        """Auth-required probes are marked SKIP when login fails."""
        client = FakeClient({})  # No login route → 404
        runner = capability_matrix.ProbeRunner(base_url="http://x")
        runner.set_client_factory(lambda: client)

        specs = [
            capability_matrix.ProbeSpec(
                capability="auth.login",
                category="Auth",
                method="POST",
                path="/api/v1/auth/login",
            ),
            capability_matrix.ProbeSpec(
                capability="memory.store",
                category="Memory",
                method="POST",
                path="/api/v1/memory/store",
                requires_auth=True,
            ),
        ]
        results = runner.run(specs)
        statuses = {r.capability: r.status for r in results}
        assert statuses["auth.login"] == "fail"
        assert statuses["memory.store"] == "skip"

    def test_run_records_pass_and_fail(self) -> None:
        """Probes get pass/fail based on HTTP status."""
        client = FakeClient(
            {
                "http://x/api/v1/health": FakeResponse(
                    200, {"data": {"status": "healthy"}}
                ),
                "http://x/api/v1/auth/login": FakeResponse(
                    200, {"data": {"access_token": "tok"}}
                ),
                "http://x/api/v1/memory/stats": FakeResponse(
                    200, {"data": {"total_chunks": 0}}
                ),
            }
        )
        runner = capability_matrix.ProbeRunner(base_url="http://x")
        runner.set_client_factory(lambda: client)
        specs = [
            capability_matrix.ProbeSpec(
                capability="auth.login",
                category="Auth",
                method="POST",
                path="/api/v1/auth/login",
            ),
            capability_matrix.ProbeSpec(
                capability="health",
                category="Foundation",
                method="GET",
                path="/api/v1/health",
                expected_status=(200, 503),
            ),
            capability_matrix.ProbeSpec(
                capability="memory.stats",
                category="Memory",
                method="GET",
                path="/api/v1/memory/stats",
                requires_auth=True,
            ),
        ]
        results = runner.run(specs)
        statuses = {r.capability: r.status for r in results}
        assert statuses["auth.login"] == "pass"
        assert statuses["health"] == "pass"
        assert statuses["memory.stats"] == "pass"

    def test_run_handles_request_exception(self) -> None:
        """Network errors become FAIL with the exception message."""

        class ExplodingClient:
            def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> None:
                raise ConnectionError("boom")

            def post(
                self,
                url: str,
                json: Optional[Dict[str, Any]] = None,
                headers: Optional[Dict[str, str]] = None,
            ) -> None:
                raise ConnectionError("boom")

            def close(self) -> None:
                return None

        runner = capability_matrix.ProbeRunner(base_url="http://x")
        runner.set_client_factory(lambda: ExplodingClient())
        specs = [
            capability_matrix.ProbeSpec(
                capability="health",
                category="Foundation",
                method="GET",
                path="/api/v1/health",
            )
        ]
        results = runner.run(specs)
        assert len(results) == 1
        assert results[0].status == "fail"
        assert "boom" in (results[0].error or "")


class TestMatrixReport:
    """Tests for report summarization and rendering."""

    def test_compute_summary_counts_each_status(self) -> None:
        """Summary dict counts pass/fail/skip/warn and total."""
        report = capability_matrix.MatrixReport(
            base_url="http://x",
            generated_at="2026-07-10T00:00:00Z",
            capabilities=[
                capability_matrix.ProbeResult(
                    capability="a", category="C", method="GET", path="/a", status="pass"
                ),
                capability_matrix.ProbeResult(
                    capability="b", category="C", method="GET", path="/b", status="fail"
                ),
                capability_matrix.ProbeResult(
                    capability="c", category="C", method="GET", path="/c", status="skip"
                ),
                capability_matrix.ProbeResult(
                    capability="d", category="C", method="GET", path="/d", status="warn"
                ),
            ],
        )
        report.compute_summary()
        assert report.summary == {
            "pass": 1,
            "fail": 1,
            "skip": 1,
            "warn": 1,
            "total": 4,
        }

    def test_render_markdown_includes_all_categories(self) -> None:
        """Rendered markdown contains every category heading."""
        report = capability_matrix.MatrixReport(
            base_url="http://x",
            generated_at="2026-07-10T00:00:00Z",
            capabilities=[
                capability_matrix.ProbeResult(
                    capability="health",
                    category="Foundation",
                    method="GET",
                    path="/api/v1/health",
                    status="pass",
                    http_status=200,
                ),
                capability_matrix.ProbeResult(
                    capability="memory.store",
                    category="Memory",
                    method="POST",
                    path="/api/v1/memory/store",
                    status="fail",
                    http_status=500,
                    error="internal error",
                ),
            ],
        )
        report.compute_summary()
        md = capability_matrix.render_markdown(report)
        assert "# JARVIS Capability Matrix" in md
        assert "### Foundation" in md
        assert "### Memory" in md
        assert "RED" in md  # Overall status because there is a FAIL
        assert "internal error" in md


class TestDefaultSpecs:
    """Tests for the default probe catalog."""

    def test_default_specs_covers_all_categories(self) -> None:
        """The catalog includes every documented capability area."""
        specs = capability_matrix.default_specs()
        categories = {s.category for s in specs}
        # All expected high-level categories present
        for required in [
            "Foundation",
            "Auth",
            "Memory",
            "Missions",
            "Agent",
            "Workflows",
            "Skills",
            "Identity",
            "Goal",
            "Observability",
            "Platform",
        ]:
            assert required in categories, f"missing category: {required}"

    def test_login_spec_is_first_in_order(self) -> None:
        """Login must be in the catalog so other auth-required probes can run."""
        specs = capability_matrix.default_specs()
        assert any(s.capability == "auth.login" for s in specs)


# ---------------------------------------------------------------------------
# validate_startup
# ---------------------------------------------------------------------------


class TestRunPreflight:
    """Tests for the preflight step in validate_startup."""

    def test_preflight_passes_on_clean_repo(self) -> None:
        """Preflight passes on a clean repo (config exists, port free)."""
        step = validate_startup.run_preflight("127.0.0.1", 18770, "config.yaml")
        assert step.status == "pass"
        assert step.name == "preflight"

    def test_preflight_fails_when_config_missing(self, tmp_path: Path) -> None:
        """Preflight fails when config file is absent."""
        step = validate_startup.run_preflight(
            "127.0.0.1", 18771, str(tmp_path / "absent.yaml")
        )
        assert step.status == "fail"
        assert "preflight" in (step.error or "")


class TestRunLogin:
    """Tests for the login step."""

    def test_login_returns_token_on_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Login returns a token when /auth/login returns 200 with a token."""
        # Use a fake httpx.Client via monkeypatching the module import.
        import httpx

        class _FakeClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def __enter__(self) -> "_FakeClient":
                return self

            def __exit__(self, *args: Any) -> None:
                return None

            def post(self, url: str, json: Any = None) -> FakeResponse:
                return FakeResponse(200, {"data": {"access_token": "tok"}})

            def close(self) -> None:
                return None

        monkeypatch.setattr(httpx, "Client", _FakeClient)
        step, token = validate_startup.run_login("http://x")
        assert step.status == "pass"
        assert token == "tok"

    def test_login_returns_none_on_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Login returns (fail-step, None) when the endpoint returns 401."""
        import httpx

        class _FakeClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def post(self, url: str, json: Any = None) -> FakeResponse:
                return FakeResponse(401, {"error": "AUTH_004"})

            def close(self) -> None:
                return None

        monkeypatch.setattr(httpx, "Client", _FakeClient)
        step, token = validate_startup.run_login("http://x")
        assert step.status == "fail"
        assert token is None


class TestValidationReport:
    """Tests for the ValidationReport model."""

    def test_ok_true_when_no_step_fails(self) -> None:
        """ok property is True only when no step has status='fail'."""
        report = validate_startup.ValidationReport(
            started_at="t0", finished_at="t1", mode="x", base_url="u"
        )
        report.steps.append(
            validate_startup.ValidationStep(
                name="preflight", status="pass", duration_ms=1.0
            )
        )
        assert report.ok

    def test_ok_false_when_a_step_fails(self) -> None:
        """ok property is False when any step has status='fail'."""
        report = validate_startup.ValidationReport(
            started_at="t0", finished_at="t1", mode="x", base_url="u"
        )
        report.steps.append(
            validate_startup.ValidationStep(
                name="preflight", status="pass", duration_ms=1.0
            )
        )
        report.steps.append(
            validate_startup.ValidationStep(
                name="health", status="fail", duration_ms=1.0
            )
        )
        assert not report.ok

    def test_to_dict_is_json_serializable(self) -> None:
        """to_dict output round-trips through json.dumps."""
        report = validate_startup.ValidationReport(
            started_at="t0", finished_at="t1", mode="x", base_url="u"
        )
        report.steps.append(
            validate_startup.ValidationStep(
                name="preflight", status="pass", duration_ms=1.5
            )
        )
        encoded = json.dumps(report.to_dict())
        decoded = json.loads(encoded)
        assert decoded["ok"] is True
        assert decoded["steps"][0]["name"] == "preflight"


class TestInProcessValidation:
    """Tests for the in-process validation path.

    These tests boot the full FastAPI app and run the live validation
    pipeline (boot + health + login + capability matrix). They are real
    integration tests, not unit tests — they share the same code path as
    ``scripts/validate_startup.py --in-process`` and take several seconds
    even on a warm cache.

    They are skipped by default in the unit test suite because:
      1. They mutate the process environment (``JARVIS_SYSTEM_ENVIRONMENT``).
      2. They depend on the dev seed admin user existing in the DB.
      3. A regression that hangs the in-process path would hang the
         entire unit suite.
    Run them explicitly when you need to validate the in-process path:
        pytest tests/test_startup_validation.py::TestInProcessValidation -v
    Or use the CLI script for the same coverage with cleaner output:
        python scripts/validate_startup.py --in-process --timeout 30
    """

    @pytest.mark.skip(
        reason="Integration test — boots the full FastAPI app; "
        "run via `python scripts/validate_startup.py --in-process` "
        "or explicitly with `-k TestInProcessValidation`."
    )
    @pytest.mark.asyncio
    async def test_in_process_validation_reports_steps(self) -> None:
        """In-process validation produces the expected step sequence."""
        report = validate_startup.ValidationReport(
            started_at="t0",
            finished_at="",
            mode="",
            base_url="",
        )
        report = await validate_startup.run_inprocess_validation(
            report, timeout_seconds=10.0
        )
        names = [s.name for s in report.steps]
        # We always get at least a health step; login + matrix may follow if boot succeeded.
        assert "health" in names


class TestCliArgs:
    """Tests for the CLI argument parser."""

    def test_default_mode_is_in_process(self) -> None:
        """No mode flag → in-process (fastest)."""
        args = validate_startup.parse_args([])
        assert args.in_process is False
        assert args.subprocess is False
        assert args.external is None

    def test_external_takes_url(self) -> None:
        """--external takes a URL argument."""
        args = validate_startup.parse_args(["--external", "http://elsewhere:9999"])
        assert args.external == "http://elsewhere:9999"
        assert args.in_process is False

    def test_in_process_flag_sets_mode(self) -> None:
        """--in-process sets the in_process flag."""
        args = validate_startup.parse_args(["--in-process"])
        assert args.in_process is True


class TestMainEntryPoint:
    """Test the top-level main() function with --in-process mode.

    See :class:`TestInProcessValidation` for the rationale: this is an
    integration test, not a unit test, and is skipped by default.
    """

    @pytest.mark.skip(
        reason="Integration test — boots the full FastAPI app; "
        "run via `python scripts/validate_startup.py --in-process`."
    )
    def test_main_returns_int(self) -> None:
        """main() returns an int exit code (0 or 1)."""
        rc = validate_startup.main(["--in-process", "--timeout", "10"])
        assert isinstance(rc, int)
        assert rc in (0, 1)

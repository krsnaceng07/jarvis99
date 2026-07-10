"""
PHASE: Platform Infrastructure
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/STARTUP_GUIDE.md (section "Automated Startup Validation")

IMPLEMENTATION PLAN:
    docs/STARTUP_GUIDE.md (section "Automated Startup Validation")

AUTHORITATIVE:
    NO

One-command JARVIS validation orchestrator.

Modes:
    --in-process      Use TestClient; fastest. Used by tests + CI.
    --subprocess      Spawn a real uvicorn instance and probe it over HTTP.
    --external URL    Probe an already-running JARVIS at the given URL.

The orchestrator:
    1. Runs preflight checks (config + venv + port).
    2. Brings up JARVIS (in-process or subprocess).
    3. Waits for /api/v1/health → 200.
    4. Logs in as the dev admin.
    5. Runs the capability matrix probe catalog.
    6. Prints a pass/fail summary.
    7. Shuts JARVIS down cleanly.

Returns non-zero exit code if any FAIL occurs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent

# Make the repo root importable so ``api.*`` / ``core.*`` / ``scripts.*``
# resolve when this script is invoked directly (``python scripts/validate_startup.py``).
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_BASE_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"

DEFAULT_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Validation result model
# ---------------------------------------------------------------------------


@dataclass
class ValidationStep:
    """A single step in the validation pipeline."""

    name: str
    status: str  # "pass" | "fail" | "skip"
    duration_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class ValidationReport:
    """Aggregated validation report."""

    started_at: str
    finished_at: str
    mode: str
    base_url: str
    steps: List[ValidationStep] = field(default_factory=list)
    capability_summary: Dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Return True only if no step FAILed."""
        return all(s.status != "fail" for s in self.steps)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict view."""
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "mode": self.mode,
            "base_url": self.base_url,
            "ok": self.ok,
            "steps": [
                {
                    "name": s.name,
                    "status": s.status,
                    "duration_ms": s.duration_ms,
                    "details": s.details,
                    "error": s.error,
                }
                for s in self.steps
            ],
            "capability_summary": self.capability_summary,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC time in ISO-8601 format."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _venv_python() -> str:
    """Return the venv Python interpreter."""
    if os.name == "nt":
        candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = ROOT / ".venv" / "bin" / "python"
    return str(candidate if candidate.exists() else sys.executable)


def _is_port_in_use(host: str, port: int, timeout: float = 0.5) -> bool:
    """Return True if a TCP socket is currently bound on (host, port)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False
        return True


# ---------------------------------------------------------------------------
# Validation steps
# ---------------------------------------------------------------------------


def run_preflight(
    host: str, port: int, config_path: str = "config.yaml"
) -> ValidationStep:
    """Run preflight checks. Returns a ValidationStep — never raises."""
    start = time.perf_counter()
    cfg_path = (ROOT / config_path).resolve()
    checks: List[Dict[str, Any]] = []

    cfg_ok = cfg_path.exists()
    checks.append({"name": "config_exists", "path": str(cfg_path), "ok": cfg_ok})

    py = _venv_python()
    py_ok = Path(py).exists() or "venv" not in py
    checks.append({"name": "venv_python", "path": py, "ok": py_ok})

    port_in_use = _is_port_in_use(host, port)
    checks.append(
        {"name": "port_free", "host": host, "port": port, "ok": not port_in_use}
    )

    ok = cfg_ok and py_ok and not port_in_use
    duration = (time.perf_counter() - start) * 1000.0
    error: Optional[str] = None
    if not ok:
        failed = [c["name"] for c in checks if not c.get("ok")]
        error = f"preflight failed: {', '.join(failed)}"

    return ValidationStep(
        name="preflight",
        status="pass" if ok else "fail",
        duration_ms=round(duration, 2),
        details={"checks": checks},
        error=error,
    )


async def wait_for_health(
    base_url: str,
    *,
    timeout_seconds: float = 30.0,
    poll_interval: float = 0.5,
) -> ValidationStep:
    """Poll /api/v1/health until 200 or timeout. Returns a ValidationStep."""
    import httpx

    start = time.perf_counter()
    url = base_url.rstrip("/") + "/api/v1/health"
    deadline = time.monotonic() + timeout_seconds
    last_status: Optional[int] = None
    last_error: Optional[str] = None

    while time.monotonic() < deadline:
        try:
            client = httpx.Client(timeout=2.0)
            try:
                response = client.get(url)
                last_status = response.status_code
                if response.status_code == 200:
                    return ValidationStep(
                        name="health",
                        status="pass",
                        duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
                        details={
                            "url": url,
                            "status_code": last_status,
                            "body": response.text,
                        },
                    )
            finally:
                client.close()
        except Exception as exc:
            last_error = str(exc)

        await asyncio.sleep(poll_interval)

    duration = (time.perf_counter() - start) * 1000.0
    return ValidationStep(
        name="health",
        status="fail",
        duration_ms=round(duration, 2),
        details={
            "url": url,
            "last_status": last_status,
            "last_error": last_error,
        },
        error=f"health probe timed out after {timeout_seconds:.1f}s",
    )


async def wait_for_health_inprocess(timeout_seconds: float = 30.0) -> ValidationStep:
    """In-process health probe via FastAPI TestClient.

    The TestClient is created ONCE (with the ``with`` block) so the FastAPI
    lifespan handler runs exactly once. Polling reuses the same booted client.
    """
    start = time.perf_counter()
    try:
        from fastapi.testclient import TestClient

        from api.main import create_app

        deadline = time.monotonic() + timeout_seconds
        last_status: Optional[int] = None
        last_error: Optional[str] = None
        last_body: Optional[str] = None

        with TestClient(create_app()) as client:
            while time.monotonic() < deadline:
                try:
                    response = client.get("/api/v1/health")
                    last_status = response.status_code
                    last_body = response.text
                    if response.status_code == 200:
                        return ValidationStep(
                            name="health",
                            status="pass",
                            duration_ms=round(
                                (time.perf_counter() - start) * 1000.0, 2
                            ),
                            details={
                                "mode": "in-process",
                                "status_code": last_status,
                                "body": last_body,
                            },
                        )
                except Exception as exc:
                    last_error = str(exc)
                await asyncio.sleep(0.2)

        return ValidationStep(
            name="health",
            status="fail",
            duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
            details={
                "mode": "in-process",
                "last_status": last_status,
                "last_body": last_body,
                "last_error": last_error,
            },
            error=f"in-process health probe timed out after {timeout_seconds:.1f}s",
        )
    except Exception as exc:
        return ValidationStep(
            name="health",
            status="fail",
            duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
            details={"mode": "in-process"},
            error=f"in-process health probe crashed: {exc}",
        )


def run_login(
    base_url: str,
    admin_username: str = "admin",
    admin_password: str = "JarvisDev123!",
    timeout: float = 5.0,
) -> Tuple[ValidationStep, Optional[str]]:
    """POST /auth/login and return the (ValidationStep, token) tuple."""
    import httpx

    start = time.perf_counter()
    url = base_url.rstrip("/") + "/api/v1/auth/login"
    payload = {"username": admin_username, "password": admin_password}
    try:
        client = httpx.Client(timeout=timeout)
        try:
            response = client.post(url, json=payload)
            duration = (time.perf_counter() - start) * 1000.0
            if response.status_code == 200:
                data = response.json()
                token = data.get("data", {}).get("access_token") or data.get(
                    "access_token"
                )
                return (
                    ValidationStep(
                        name="login",
                        status="pass",
                        duration_ms=round(duration, 2),
                        details={
                            "status_code": response.status_code,
                            "username": admin_username,
                            "has_token": bool(token),
                        },
                    ),
                    token,
                )
            return (
                ValidationStep(
                    name="login",
                    status="fail",
                    duration_ms=round(duration, 2),
                    details={
                        "status_code": response.status_code,
                        "body": response.text[:500],
                    },
                    error=f"login returned {response.status_code}",
                ),
                None,
            )
        finally:
            client.close()
    except Exception as exc:
        duration = (time.perf_counter() - start) * 1000.0
        return (
            ValidationStep(
                name="login",
                status="fail",
                duration_ms=round(duration, 2),
                details={"url": url},
                error=f"login request failed: {exc}",
            ),
            None,
        )


# ---------------------------------------------------------------------------
# Uvicorn lifecycle helper (subprocess mode)
# ---------------------------------------------------------------------------


class UvicornProcess:
    """Context manager wrapping a uvicorn subprocess for validation."""

    def __init__(self, host: str, port: int, config_path: str) -> None:
        self.host = host
        self.port = port
        self.config_path = config_path
        self._proc: Optional[subprocess.Popen[bytes]] = None
        self._log_path: Optional[Path] = None

    def __enter__(self) -> "UvicornProcess":
        log_dir = ROOT / ".audit"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / f"validate_startup_{int(time.time())}.log"

        env = os.environ.copy()
        env["JARVIS_CONFIG_PATH"] = str((ROOT / self.config_path).resolve())

        cmd = [
            _venv_python(),
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--log-level",
            "info",
        ]
        log_file = open(self._log_path, "w", encoding="utf-8")
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            ),
        )
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                if os.name == "nt":
                    self._proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    self._proc.send_signal(signal.SIGTERM)
                try:
                    self._proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=5)
            except Exception:
                pass

    @property
    def log_path(self) -> Optional[Path]:
        """Return the log file path (if any)."""
        return self._log_path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def run_inprocess_validation(
    report: ValidationReport,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT,
) -> ValidationReport:
    """Run validation entirely in-process (fastest path).

    The app is booted ONCE at the start (lifespan + Kernel), and the same
    ``TestClient`` is reused across health, login, and capability-matrix steps.
    """
    from fastapi.testclient import TestClient

    from api.main import create_app

    report.mode = "in-process"
    report.base_url = "in-process"

    # Local dev validation needs the dev seed (admin + roles). If the caller
    # already pinned the environment, leave it alone; otherwise default to
    # "development" so the seed admin is created on first boot.
    os.environ.setdefault("JARVIS_SYSTEM_ENVIRONMENT", "development")

    app = create_app()
    started = time.perf_counter()
    try:
        client_cm: Any = TestClient(app)
        client = client_cm.__enter__()
    except Exception as exc:
        report.steps.append(
            ValidationStep(
                name="boot",
                status="fail",
                duration_ms=round((time.perf_counter() - started) * 1000.0, 2),
                error=f"app boot crashed: {exc}",
            )
        )
        report.finished_at = _now_iso()
        return report

    boot_duration = (time.perf_counter() - started) * 1000.0
    report.steps.append(
        ValidationStep(
            name="boot",
            status="pass",
            duration_ms=round(boot_duration, 2),
            details={"mode": "in-process"},
        )
    )

    try:
        # 1. Health (in-process, reused client)
        health_step = await _probe_health_with_client(
            client, timeout_seconds=timeout_seconds
        )
        report.steps.append(health_step)
        if health_step.status != "pass":
            report.finished_at = _now_iso()
            return report

        # 2. Login via TestClient
        start = time.perf_counter()
        try:
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "JarvisDev123!"},
            )
            duration = (time.perf_counter() - start) * 1000.0
            if response.status_code == 200:
                data = response.json()
                token = data.get("data", {}).get("access_token") or data.get(
                    "access_token"
                )
                report.steps.append(
                    ValidationStep(
                        name="login",
                        status="pass",
                        duration_ms=round(duration, 2),
                        details={
                            "status_code": response.status_code,
                            "has_token": bool(token),
                        },
                    )
                )
            else:
                report.steps.append(
                    ValidationStep(
                        name="login",
                        status="fail",
                        duration_ms=round(duration, 2),
                        details={
                            "status_code": response.status_code,
                            "body": response.text[:500],
                        },
                        error=f"login returned {response.status_code}",
                    )
                )
                report.finished_at = _now_iso()
                return report
        except Exception as exc:
            report.steps.append(
                ValidationStep(
                    name="login",
                    status="fail",
                    duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
                    error=f"login request failed: {exc}",
                )
            )
            report.finished_at = _now_iso()
            return report

        # 3. Capability matrix (uses the same booted TestClient)
        from scripts.capability_matrix import ProbeRunner, default_specs

        runner = ProbeRunner(
            base_url="http://testserver",
            admin_username="admin",
            admin_password="JarvisDev123!",
        )
        runner.set_client_factory(lambda: _InProcessClient(client))
        capabilities = runner.run(default_specs())

        summary = {"pass": 0, "fail": 0, "skip": 0, "warn": 0, "total": 0}
        for c in capabilities:
            summary[c.status] = summary.get(c.status, 0) + 1
            summary["total"] += 1
        report.capability_summary = summary

        if summary.get("fail", 0) == 0:
            report.steps.append(
                ValidationStep(
                    name="capability_matrix",
                    status="pass",
                    duration_ms=0.0,
                    details={"summary": summary},
                )
            )
        else:
            failed = [c.capability for c in capabilities if c.status == "fail"]
            report.steps.append(
                ValidationStep(
                    name="capability_matrix",
                    status="fail",
                    duration_ms=0.0,
                    details={"summary": summary, "failed": failed},
                    error=f"{len(failed)} capability probe(s) failed: {failed[:5]}",
                )
            )
    finally:
        try:
            client_cm.__exit__(None, None, None)
        except Exception:
            pass

    report.finished_at = _now_iso()
    return report


async def _probe_health_with_client(
    client: Any,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT,
) -> ValidationStep:
    """Probe /api/v1/health using an already-booted TestClient."""
    import time

    start = time.perf_counter()
    deadline = start + timeout_seconds
    last_status: Optional[int] = None
    last_body: Optional[str] = None
    last_error: Optional[str] = None

    while time.monotonic() < deadline:
        try:
            response = client.get("/api/v1/health")
            last_status = response.status_code
            last_body = response.text
            if response.status_code == 200:
                return ValidationStep(
                    name="health",
                    status="pass",
                    duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
                    details={
                        "mode": "in-process",
                        "status_code": last_status,
                        "body": last_body,
                    },
                )
        except Exception as exc:
            last_error = str(exc)
        await asyncio.sleep(0.2)

    return ValidationStep(
        name="health",
        status="fail",
        duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
        details={
            "mode": "in-process",
            "last_status": last_status,
            "last_body": last_body,
            "last_error": last_error,
        },
        error=f"in-process health probe timed out after {timeout_seconds:.1f}s",
    )


class _InProcessClient:
    """Adapter that turns TestClient into an httpx-style client for the matrix.

    Accepts either an already-booted TestClient (preferred — reuses the same
    lifespan/Kernel state) or an app factory callable (legacy path that boots
    its own client per probe).
    """

    def __init__(self, source: Any) -> None:
        from fastapi.testclient import TestClient

        # If ``source`` is callable, treat it as an app factory and create a
        # fresh TestClient. Otherwise assume it's an already-built TestClient.
        if callable(source):
            self._app_factory = source
            self._client = TestClient(source())
        else:
            self._app_factory = None
            self._client = source

    def _ensure_login_token(self) -> None:
        """No-op here; token is set explicitly via set_token()."""
        return None

    def set_token(self, token: Optional[str]) -> None:
        """Store the bearer token used by auth-required probes."""
        self._token = token

    _token: Optional[str] = None

    def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> Any:
        kwargs: Dict[str, Any] = {}
        if self._token and headers is None:
            headers = {"Authorization": f"Bearer {self._token}"}
        if headers:
            kwargs["headers"] = headers
        return self._client.get(url, **kwargs)

    def post(
        self,
        url: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        kwargs: Dict[str, Any] = {}
        if json is not None:
            kwargs["json"] = json
        if self._token and headers is None:
            headers = {"Authorization": f"Bearer {self._token}"}
        if headers:
            kwargs["headers"] = headers
        return self._client.post(url, **kwargs)

    def close(self) -> None:
        return None


async def run_subprocess_validation(
    report: ValidationReport,
    host: str,
    port: int,
    config_path: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT,
) -> ValidationReport:
    """Run validation by spawning uvicorn and probing it over HTTP."""
    report.mode = "subprocess"
    report.base_url = f"http://{host}:{port}"

    # 1. Preflight
    pf = run_preflight(host, port, config_path)
    report.steps.append(pf)
    if pf.status != "pass":
        report.finished_at = _now_iso()
        return report

    # 2. Spawn uvicorn and probe
    with UvicornProcess(host, port, config_path) as proc:
        health_step = await wait_for_health(
            report.base_url, timeout_seconds=timeout_seconds
        )
        report.steps.append(health_step)
        if health_step.status != "pass":
            report.finished_at = _now_iso()
            return report

        login_step, _token = run_login(report.base_url)
        report.steps.append(login_step)
        if login_step.status != "pass":
            report.finished_at = _now_iso()
            return report

        # 3. Capability matrix over real HTTP
        from scripts.capability_matrix import ProbeRunner, default_specs

        runner = ProbeRunner(
            base_url=report.base_url,
            admin_username="admin",
            admin_password="JarvisDev123!",
        )
        runner.login("admin", "JarvisDev123!")
        capabilities = runner.run(default_specs())

        summary = {"pass": 0, "fail": 0, "skip": 0, "warn": 0, "total": 0}
        for c in capabilities:
            summary[c.status] = summary.get(c.status, 0) + 1
            summary["total"] += 1
        report.capability_summary = summary

        if summary.get("fail", 0) == 0:
            report.steps.append(
                ValidationStep(
                    name="capability_matrix",
                    status="pass",
                    duration_ms=0.0,
                    details={"summary": summary, "log": str(proc.log_path)},
                )
            )
        else:
            failed = [c.capability for c in capabilities if c.status == "fail"]
            report.steps.append(
                ValidationStep(
                    name="capability_matrix",
                    status="fail",
                    duration_ms=0.0,
                    details={
                        "summary": summary,
                        "failed": failed,
                        "log": str(proc.log_path),
                    },
                    error=f"{len(failed)} capability probe(s) failed: {failed[:5]}",
                )
            )

    report.finished_at = _now_iso()
    return report


async def run_external_validation(
    report: ValidationReport, base_url: str
) -> ValidationReport:
    """Run validation against an already-running JARVIS at base_url."""
    report.mode = "external"
    report.base_url = base_url

    health_step = await wait_for_health(base_url, timeout_seconds=15.0)
    report.steps.append(health_step)
    if health_step.status != "pass":
        report.finished_at = _now_iso()
        return report

    login_step, _token = run_login(base_url)
    report.steps.append(login_step)
    if login_step.status != "pass":
        report.finished_at = _now_iso()
        return report

    from scripts.capability_matrix import ProbeRunner, default_specs

    runner = ProbeRunner(base_url=base_url)
    runner.login("admin", "JarvisDev123!")
    capabilities = runner.run(default_specs())

    summary = {"pass": 0, "fail": 0, "skip": 0, "warn": 0, "total": 0}
    for c in capabilities:
        summary[c.status] = summary.get(c.status, 0) + 1
        summary["total"] += 1
    report.capability_summary = summary

    if summary.get("fail", 0) == 0:
        report.steps.append(
            ValidationStep(
                name="capability_matrix",
                status="pass",
                duration_ms=0.0,
                details={"summary": summary},
            )
        )
    else:
        failed = [c.capability for c in capabilities if c.status == "fail"]
        report.steps.append(
            ValidationStep(
                name="capability_matrix",
                status="fail",
                duration_ms=0.0,
                details={"summary": summary, "failed": failed},
                error=f"{len(failed)} capability probe(s) failed: {failed[:5]}",
            )
        )

    report.finished_at = _now_iso()
    return report


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(
        prog="validate_startup.py",
        description="Validate a JARVIS OS startup end-to-end.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--in-process",
        action="store_true",
        help="Run validation in-process via FastAPI TestClient",
    )
    mode.add_argument(
        "--subprocess",
        action="store_true",
        help="Spawn uvicorn as a subprocess and probe it",
    )
    mode.add_argument(
        "--external",
        metavar="URL",
        help="Validate an already-running JARVIS at the given URL",
    )

    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--report-json",
        default=str(ROOT / ".audit" / "startup_validation.json"),
        help="Path to write the JSON validation report",
    )
    parser.add_argument(
        "--fail-on-fail",
        action="store_true",
        help="Exit non-zero on any FAIL (default behaviour anyway)",
    )
    return parser.parse_args(argv)


def print_summary(report: ValidationReport) -> None:
    """Pretty-print the validation summary to stdout."""
    print()
    print("=" * 70)
    print("JARVIS Startup Validation")
    print("=" * 70)
    print(f"Mode:       {report.mode}")
    print(f"Base URL:   {report.base_url}")
    print(f"Started:    {report.started_at}")
    print(f"Finished:   {report.finished_at}")
    print()
    print(f"{'STEP':<22} {'STATUS':<8} {'DURATION':<12} ERROR")
    print("-" * 70)
    for step in report.steps:
        err = (step.error or "")[:50]
        print(f"{step.name:<22} {step.status:<8} {step.duration_ms:>8.1f}ms   {err}")

    if report.capability_summary:
        s = report.capability_summary
        print()
        print(
            f"Capability matrix: {s.get('pass', 0)} pass, "
            f"{s.get('fail', 0)} fail, "
            f"{s.get('skip', 0)} skip, "
            f"{s.get('warn', 0)} warn"
        )
    print()
    print(f"OVERALL: {'PASS' if report.ok else 'FAIL'}")
    print("=" * 70)


async def main_async(args: argparse.Namespace) -> int:
    """Async entry point."""
    report = ValidationReport(
        started_at=_now_iso(),
        finished_at="",
        mode="",
        base_url="",
    )

    if args.external:
        report = await run_external_validation(report, args.external)
    elif args.subprocess:
        report = await run_subprocess_validation(
            report,
            args.host,
            args.port,
            args.config,
            timeout_seconds=args.timeout,
        )
    else:
        # Default: in-process (fastest, used by tests/CI)
        report = await run_inprocess_validation(report, timeout_seconds=args.timeout)

    # Write JSON report
    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"[validate] wrote JSON report: {report_path}")

    print_summary(report)

    return 0 if report.ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    """Sync entry point."""
    args = parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())

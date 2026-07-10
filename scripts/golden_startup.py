"""
PHASE: Platform Infrastructure
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/STARTUP_GUIDE.md

IMPLEMENTATION PLAN:
    docs/STARTUP_GUIDE.md (section "Programmatic Startup API")

AUTHORITATIVE:
    NO

Programmatic counterpart to run.py. Used by:
    - tests (start/stop a JARVIS instance under TestClient mode)
    - scripts/validate_startup.py (subprocess boot for live validation)
    - scripts/capability_matrix.py (probes a running instance)

Public API:
    StartupConfig      — dataclass describing bind host/port/config path
    StartupResult      — dataclass describing the outcome of a startup run
    preflight_checks() — returns StartupResult; never raises
    boot_kernel()      — boots Kernel in-process and returns the instance
    run_uvicorn()      — runs uvicorn in-process (used by tests with TestClient
                         via fastapi.testclient against the returned app)
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent

logger = logging.getLogger("jarvis.scripts.golden_startup")


@dataclass
class StartupConfig:
    """Configuration for one JARVIS startup run."""

    host: str = "127.0.0.1"
    port: int = 8765
    config_path: str = "config.yaml"
    reload: bool = False
    workers: int = 1
    skip_preflight: bool = False
    extra_env: Dict[str, str] = field(default_factory=dict)

    @property
    def resolved_config_path(self) -> Path:
        """Return the absolute path to the YAML config file."""
        return (ROOT / self.config_path).resolve()


@dataclass
class StartupResult:
    """Outcome of a startup attempt (preflight or boot)."""

    ok: bool
    stage: str
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict view of this result."""
        return {
            "ok": self.ok,
            "stage": self.stage,
            "details": self.details,
            "error": self.error,
        }


def _is_port_in_use(host: str, port: int, timeout: float = 0.5) -> bool:
    """Return True if the given TCP port is bound on the host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False
        return True


def _venv_python() -> str:
    """Return the Python interpreter inside the project virtualenv."""
    if os.name == "nt":
        candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = ROOT / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def preflight_checks(
    config: StartupConfig,
    *,
    python_executable: Optional[str] = None,
) -> StartupResult:
    """Run all preflight checks (config, venv, port) without raising.

    Args:
        config: Startup configuration to validate.
        python_executable: Optional override (used by tests to avoid filesystem checks).

    Returns:
        StartupResult with stage='preflight' and ok=True only if all checks pass.
    """
    checks: List[Dict[str, Any]] = []

    cfg_path = config.resolved_config_path
    cfg_ok = cfg_path.exists()
    checks.append({"name": "config_exists", "path": str(cfg_path), "ok": cfg_ok})
    if not cfg_ok:
        return StartupResult(
            ok=False,
            stage="preflight",
            details={"checks": checks},
            error=f"config not found: {cfg_path}",
        )

    if python_executable is None:
        py = _venv_python()
        py_path = Path(py)
        py_ok = py_path.exists()
        checks.append({"name": "venv_python", "path": py, "ok": py_ok})
        if not py_ok and "venv" in str(py_path):
            return StartupResult(
                ok=False,
                stage="preflight",
                details={"checks": checks},
                error=".venv not found — run `uv sync` to bootstrap it",
            )

    port_in_use = _is_port_in_use(config.host, config.port)
    checks.append(
        {
            "name": "port_free",
            "host": config.host,
            "port": config.port,
            "ok": not port_in_use,
        }
    )
    if port_in_use:
        return StartupResult(
            ok=False,
            stage="preflight",
            details={"checks": checks},
            error=(
                f"port {config.port} already in use on {config.host}; "
                "stop the running process or pass a different --port"
            ),
        )

    return StartupResult(
        ok=True,
        stage="preflight",
        details={"checks": checks, "python": _venv_python()},
    )


async def boot_kernel(
    config_path: Optional[str] = None,
) -> Any:
    """Boot the JARVIS Kernel in-process and return the live Kernel instance.

    Args:
        config_path: Optional override; defaults to config.yaml at repo root.

    Returns:
        The booted ``core.kernel.Kernel`` instance with services registered.

    Raises:
        RuntimeError: If ``Kernel.boot()`` returns False.
        ImportError: If core modules cannot be imported (broken install).
    """
    cfg = config_path or str(ROOT / "config.yaml")
    os.environ["JARVIS_CONFIG_PATH"] = cfg

    from core.kernel import Kernel

    kernel = Kernel()
    await kernel.initialize()
    ok = await kernel.boot(cfg)
    if not ok:
        raise RuntimeError("Kernel.boot() returned False")
    return kernel


def create_app() -> Any:
    """Build the FastAPI app via the standard factory.

    Equivalent to ``import api.main`` but defers the import until needed.
    """
    from api.main import create_app as _create_app

    return _create_app()


async def wait_for_health(
    base_url: str,
    *,
    timeout_seconds: float = 30.0,
    poll_interval: float = 0.5,
    client_factory: Optional[Callable[[], Any]] = None,
) -> StartupResult:
    """Poll a JARVIS instance's /api/v1/health endpoint until it returns 200.

    Args:
        base_url: e.g. http://127.0.0.1:8765
        timeout_seconds: Total time to wait before giving up.
        poll_interval: Seconds between probes.
        client_factory: Optional factory returning an HTTP client with .get().
                        Used by tests; default uses httpx.

    Returns:
        StartupResult with stage='health' and ok=True when /health returns 200.
    """
    import time

    deadline = time.monotonic() + timeout_seconds
    url = base_url.rstrip("/") + "/api/v1/health"

    if client_factory is None:
        import httpx

        def client_factory() -> httpx.Client:
            return httpx.Client(timeout=2.0)

    last_status: Optional[int] = None
    last_body: Optional[str] = None
    last_error: Optional[str] = None

    while time.monotonic() < deadline:
        client = client_factory()
        try:
            response = client.get(url)
            last_status = response.status_code
            last_body = response.text
            if response.status_code == 200:
                return StartupResult(
                    ok=True,
                    stage="health",
                    details={
                        "url": url,
                        "status_code": last_status,
                        "body": last_body,
                    },
                )
        except Exception as exc:
            last_error = str(exc)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        await asyncio.sleep(poll_interval)

    return StartupResult(
        ok=False,
        stage="health",
        details={
            "url": url,
            "last_status": last_status,
            "last_body": last_body,
            "last_error": last_error,
        },
        error=f"health probe timed out after {timeout_seconds:.1f}s",
    )


def resolve_command(config: StartupConfig) -> List[str]:
    """Resolve the uvicorn subprocess command for the given config.

    By default (workers=1) we do NOT emit --workers; uvicorn runs single-process
    which is the recommended dev mode. --workers is only added when explicitly
    requested and reload is off.
    """
    cmd = [
        _venv_python(),
        "-m",
        "uvicorn",
        "api.main:app",
        "--host",
        config.host,
        "--port",
        str(config.port),
    ]
    if config.reload:
        cmd.append("--reload")
    elif config.workers and config.workers > 1:
        cmd.extend(["--workers", str(config.workers)])
    return cmd


def run_uvicorn(config: StartupConfig) -> int:
    """Run uvicorn as a blocking subprocess. Returns the process exit code."""
    import subprocess

    env = os.environ.copy()
    env["JARVIS_CONFIG_PATH"] = str(config.resolved_config_path)
    for key, value in config.extra_env.items():
        env[key] = value

    cmd = resolve_command(config)
    logger.info("Launching uvicorn: %s", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


async def run_inprocess_healthcheck(
    timeout_seconds: float = 30.0,
) -> StartupResult:
    """Boot the Kernel in-process and probe its health directly via TestClient.

    This is the fastest, most reliable validation path — used by tests and
    ``scripts/validate_startup.py`` when ``--in-process`` is passed.
    """
    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app()

    def _probe() -> Any:
        client = TestClient(app)
        return client.get("/api/v1/health")

    return await wait_for_health(
        "http://testserver",
        timeout_seconds=timeout_seconds,
        poll_interval=0.1,
        client_factory=lambda: _InProcessClient(_probe),
    )


class _InProcessClient:
    """Adapter so ``wait_for_health`` can use a TestClient-like object."""

    def __init__(self, probe: Callable[[], Any]) -> None:
        self._probe = probe

    def get(self, url: str) -> Any:
        response = self._probe()
        return response

    def close(self) -> None:
        return None

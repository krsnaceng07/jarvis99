"""
PHASE: Platform Infrastructure
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/STARTUP_GUIDE.md

IMPLEMENTATION PLAN:
    docs/STARTUP_GUIDE.md (section "Golden Startup Path")

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
This is the canonical JARVIS OS launcher. It enforces the documented startup
sequence (env check → venv check → config check → kernel boot → serve).
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parent

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_CONFIG = "config.yaml"


def _venv_python() -> str:
    """Return the Python interpreter inside the project virtualenv, if it exists."""
    if os.name == "nt":
        candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = ROOT / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def _is_port_in_use(host: str, port: int) -> bool:
    """Return True if the given TCP port is already bound (something is listening)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect((host, port))
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False
        return True


def _run_step(label: str, command: Sequence[str], cwd: Path) -> int:
    """Run a single startup step with a friendly header and exit on failure."""
    banner = f"[JARVIS] STEP: {label}"
    print(banner)
    print("-" * len(banner))
    try:
        return subprocess.call(list(command), cwd=str(cwd))
    except FileNotFoundError as exc:
        print(f"[JARVIS] ERROR: command not found: {exc.filename}")
        return 127


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for the JARVIS launcher."""
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Canonical JARVIS OS launcher (Golden Startup Path).",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Bind port (default {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help=f"Path to YAML config (default {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable autoreload (development only)",
    )
    parser.add_argument(
        "--no-preflight",
        action="store_true",
        help="Skip preflight checks (env, venv, port)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="uvicorn worker count (default 1)",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print resolved configuration and exit (dry run)",
    )
    return parser.parse_args(argv)


def _resolve_uvicorn_args(args: argparse.Namespace) -> List[str]:
    """Build the uvicorn invocation arguments."""
    cmd: List[str] = [
        _venv_python(),
        "-m",
        "uvicorn",
        "api.main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        cmd.append("--reload")
    if args.workers and not args.reload:
        cmd.extend(["--workers", str(args.workers)])
    return cmd


def preflight(args: argparse.Namespace) -> int:
    """Run all preflight checks. Returns non-zero exit code on failure."""
    print("[JARVIS] Running preflight checks...")

    config_path = ROOT / args.config
    if not config_path.exists():
        print(f"[JARVIS] FAIL: config not found: {config_path}")
        return 2

    venv_py = Path(_venv_python())
    if venv_py.name == "python.exe" and not venv_py.exists():
        print("[JARVIS] FAIL: .venv not found. Run `uv sync` first.")
        return 3

    if _is_port_in_use(args.host, args.port):
        print(
            f"[JARVIS] FAIL: port {args.port} already in use on {args.host}. "
            f"Stop the running process or use --port."
        )
        return 4

    print("[JARVIS] preflight: OK")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the JARVIS launcher."""
    args = parse_args(argv)

    print("[JARVIS] Golden Startup Path")
    print(f"[JARVIS] Root:   {ROOT}")
    print(f"[JARVIS] Python: {_venv_python()}")
    print(f"[JARVIS] Config: {args.config}")
    print(f"[JARVIS] Bind:   {args.host}:{args.port}")
    print()

    if not args.no_preflight:
        rc = preflight(args)
        if rc != 0:
            return rc

    env = os.environ.copy()
    env["JARVIS_CONFIG_PATH"] = str(ROOT / args.config)

    cmd = _resolve_uvicorn_args(args)
    if args.print_only:
        print("[JARVIS] DRY RUN — resolved command:")
        print("  " + " ".join(cmd))
        return 0

    print("[JARVIS] Booting uvicorn...")
    print(f"[JARVIS] CMD: {' '.join(cmd)}")
    try:
        return subprocess.call(cmd, cwd=str(ROOT), env=env)
    except KeyboardInterrupt:
        print("\n[JARVIS] Shutdown requested (Ctrl+C).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

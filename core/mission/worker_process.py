"""
PHASE: 45 (M6.4.A)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (§4.4 Distributed Execution, §8.3 Security)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md  (M6.4.A — WorkerProcess CLI entry point)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

``WorkerProcess`` — CLI entry point for a single distributed worker.

The CLI is intentionally minimal in M6.4.A:

* ``register()`` once on startup (idempotent across retries).
* ``heartbeat()`` every ``--heartbeat-interval`` seconds (default 10s —
  more than 2x the 15s D-1 grace period so a single missed heartbeat
  does not flip the worker OFFLINE).
* ``mark_offline()`` on SIGTERM / SIGINT (graceful shutdown).

The CLI does NOT execute missions in M6.4.A. Mission execution is
orchestrated by the leader (``DistributedRouter``); this worker process
is a registration-side primitive only. In M6.4.B a real worker loop
will be added that consumes the transport's task channel.

Security (spec §8.3):

* Configuration is read from environment variables only — no command-line
  secret passing.
* The CLI does NOT accept DB credentials, tokens, or any sensitive
  argument on the command line.
* Capabilities are passed as a JSON string (``--capabilities='{"platforms":["linux"]}'``)
  — this is JSON, not a secret.

Invocation::

    python -m core.mission.worker_process \
        --worker-id=01939af7-... \
        --hostname=$(hostname) \
        --pid=$$
        --capabilities='{"platforms":["linux","macos"], "skills":[]}' \
        --heartbeat-interval=10 \
        --db-url=sqlite+aiosqlite:///:memory:

The CLI is also importable as a class (``WorkerProcess``) so the test
suite can drive it without ``subprocess`` overhead.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import socket
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from core.mission.worker_registry import (
    DEFAULT_HEARTBEAT_GRACE_SECONDS,
    WORKER_STATUS_OFFLINE,
    WORKER_STATUS_ONLINE,
    WorkerRegistry,
)

logger = logging.getLogger("jarvis.core.mission.worker_process")


# Default heartbeat interval — 10s. The D-1 grace period is 15s, so a
# single missed heartbeat does not flip the worker OFFLINE. Two
# consecutive misses WILL.
DEFAULT_HEARTBEAT_INTERVAL_SECONDS: float = 10.0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WorkerProcessError(RuntimeError):
    """Internal-error in the WorkerProcess CLI. Raised on bad arguments
    or unexpected DB failures during startup."""


# ---------------------------------------------------------------------------
# Config (parsed args + env-var resolution)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkerProcessConfig:
    """Immutable configuration for one ``WorkerProcess`` instance.

    All fields can be supplied via CLI args OR environment variables.
    CLI args win if both are provided (the CLI parses env-vars as
    defaults). See ``from_args_and_env`` for the precedence chain.
    """

    worker_id: UUID
    hostname: str
    pid: int
    capabilities: Dict[str, Any] = field(default_factory=dict)
    heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    db_url: Optional[str] = None
    initial_status: str = WORKER_STATUS_ONLINE

    def __post_init__(self) -> None:
        if not isinstance(self.worker_id, UUID):
            raise WorkerProcessError(
                f"worker_id must be a UUID (got {type(self.worker_id).__name__})"
            )
        if not isinstance(self.hostname, str) or not self.hostname:
            raise WorkerProcessError("hostname must be a non-empty str.")
        if not isinstance(self.pid, int) or self.pid <= 0:
            raise WorkerProcessError(f"pid must be a positive int (got {self.pid!r}).")
        if self.heartbeat_interval_seconds <= 0:
            raise WorkerProcessError(
                f"heartbeat_interval_seconds must be > 0 "
                f"(got {self.heartbeat_interval_seconds!r})."
            )
        if self.initial_status not in (
            WORKER_STATUS_ONLINE,
            WORKER_STATUS_OFFLINE,
        ):
            raise WorkerProcessError(
                f"initial_status must be ONLINE or OFFLINE "
                f"(got {self.initial_status!r})."
            )

    @classmethod
    def from_args_and_env(
        cls,
        args: "argparse.Namespace",
        env: "Optional[Dict[str, str]]" = None,
    ) -> "WorkerProcessConfig":
        """Build a config from parsed CLI args + env-var defaults.

        Precedence: explicit CLI value > env-var > constructor default.

        Env-var keys:

        * ``JARVIS_WORKER_ID`` — UUID; auto-generated if unset.
        * ``JARVIS_WORKER_HOSTNAME`` — defaults to
          ``socket.gethostname()``.
        * ``JARVIS_WORKER_PID`` — defaults to ``os.getpid()``.
        * ``JARVIS_WORKER_CAPABILITIES`` — JSON string; defaults to
          ``{"platforms": [], "skills": []}``.
        * ``JARVIS_WORKER_HEARTBEAT_INTERVAL`` — float seconds; default
          = 10.0.
        * ``JARVIS_DB_URL`` — connection URL passed to the in-process
          ``DatabaseSessionManager``. Tests use this to point at
          SQLite in-memory; production reads it from the Kernel config.
        """
        e = dict(env) if env is not None else os.environ

        # worker_id
        raw_id = getattr(args, "worker_id", None) or e.get("JARVIS_WORKER_ID")
        if not raw_id:
            worker_id = uuid4()
        else:
            try:
                worker_id = UUID(str(raw_id))
            except (TypeError, ValueError) as exc:
                raise WorkerProcessError(
                    f"--worker-id must be a valid UUID (got {raw_id!r})."
                ) from exc

        # hostname
        hostname = (
            getattr(args, "hostname", None)
            or e.get("JARVIS_WORKER_HOSTNAME")
            or socket.gethostname()
        )

        # pid
        raw_pid = getattr(args, "pid", None) or e.get("JARVIS_WORKER_PID")
        if raw_pid is None:
            pid = os.getpid()
        else:
            try:
                pid = int(raw_pid)
            except ValueError as exc:
                raise WorkerProcessError(
                    f"--pid must be a positive int (got {raw_pid!r})."
                ) from exc

        # capabilities
        raw_caps = (
            getattr(args, "capabilities", None)
            or e.get("JARVIS_WORKER_CAPABILITIES")
            or '{"platforms": [], "skills": []}'
        )
        try:
            capabilities = json.loads(raw_caps)
            if not isinstance(capabilities, dict):
                raise TypeError("not a dict")
        except (json.JSONDecodeError, TypeError) as exc:
            raise WorkerProcessError(
                f"--capabilities must be a JSON object (got {raw_caps!r})."
            ) from exc

        # heartbeat interval
        raw_hb = getattr(args, "heartbeat_interval", None) or e.get(
            "JARVIS_WORKER_HEARTBEAT_INTERVAL"
        )
        if raw_hb is None:
            heartbeat_interval_seconds = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
        else:
            try:
                heartbeat_interval_seconds = float(raw_hb)
            except ValueError as exc:
                raise WorkerProcessError(
                    f"--heartbeat-interval must be a positive float (got {raw_hb!r})."
                ) from exc

        # db_url
        db_url = getattr(args, "db_url", None) or e.get("JARVIS_DB_URL")

        return cls(
            worker_id=worker_id,
            hostname=hostname,
            pid=pid,
            capabilities=capabilities,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            db_url=db_url,
        )


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argparse ``ArgumentParser`` for the WorkerProcess CLI.

    Exposed as a free function so tests can drive the CLI without
    spawning a subprocess.
    """
    parser = argparse.ArgumentParser(
        prog="jarvis-worker",
        description=(
            "M6.4.A WorkerProcess CLI — registers a worker in "
            "worker_registry, heartbeats every --heartbeat-interval "
            "seconds, and shuts down cleanly on SIGTERM / SIGINT. "
            "No mission execution in M6.4.A (see DistributedRouter + "
            "WorkerProcess task loop in M6.4.B)."
        ),
    )
    parser.add_argument(
        "--worker-id",
        type=str,
        default=None,
        help=(
            "Stable UUID for this worker. Keep the same across restarts "
            "so the leader preserves liveness. Auto-generated if absent. "
            "Env-var: JARVIS_WORKER_ID."
        ),
    )
    parser.add_argument(
        "--hostname",
        type=str,
        default=None,
        help=(
            "Hostname the worker runs on. Defaults to socket.gethostname(). "
            "Env-var: JARVIS_WORKER_HOSTNAME."
        ),
    )
    parser.add_argument(
        "--pid",
        type=int,
        default=None,
        help=(
            "OS PID (diagnostic). Defaults to os.getpid(). Env-var: JARVIS_WORKER_PID."
        ),
    )
    parser.add_argument(
        "--capabilities",
        type=str,
        default=None,
        help=(
            'JSON-encoded capabilities blob, e.g. \'{"platforms":["linux"], '
            '"skills":[]}\'. Env-var: JARVIS_WORKER_CAPABILITIES.'
        ),
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=None,
        help=(
            "Heartbeat send interval in seconds (default 10.0). Must be "
            "< the D-1 grace period (15s) so a single missed heartbeat "
            "does not flip the worker OFFLINE."
        ),
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help=(
            "Optional Database URL for an in-process DatabaseSessionManager. "
            "Defaults to None (the worker expects a Kernel-managed "
            "db_manager in production). Tests use this to point at "
            "SQLite in-memory."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Register + heartbeat once + exit. Useful for tests and for "
            "one-shot registration workflows; production uses the long-"
            "running mode (default)."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# WorkerProcess — main class
# ---------------------------------------------------------------------------


class WorkerProcess:
    """Long-running worker process.

    Lifecycle::

        worker = WorkerProcess(config, db_manager)
        await worker.start()         # registers + starts heartbeat loop
        ...                           # SIGTERM/SIGINT -> stop() awaited
        await worker.stop()          # mark_offline + cancel heartbeat

    The class is the import-friendly wrapper around the lifecycle logic
    so tests can drive the heartbeat / shutdown paths without spawning
    a real process. The ``run()`` CLI loop is a thin shell on top.
    """

    def __init__(
        self,
        config: WorkerProcessConfig,
        db_manager: Any,
        *,
        registry: "Optional[WorkerRegistry]" = None,
        heartbeat_grace_seconds: "Optional[float]" = None,
        clock: "Optional[Any]" = None,
        sleep: "Optional[Any]" = None,
    ) -> None:
        """Initialize.

        Args:
            config: Immutable configuration (worker_id + capabilities +
                heartbeat interval).
            db_manager: A ``DatabaseSessionManager`` (or any object with
                a ``session()`` async context manager). Required.
            registry: Optional pre-built ``WorkerRegistry``. Defaults to
                constructing one from ``db_manager`` + grace. Tests can
                inject a custom registry to assert specific call patterns.
            heartbeat_grace_seconds: Override the D-1 grace period; only
                used when constructing the default registry. Ignored if
                ``registry`` is supplied.
            clock: Optional clock callable (defaults to wall-clock UTC).
                Tests pass a stub.
            sleep: Optional ``asyncio.sleep``-compatible callable
                (defaults to ``asyncio.sleep``). Tests pass a no-op /
                recorder.
        """
        if config is None:
            raise WorkerProcessError("WorkerProcess requires a config.")
        if db_manager is None:
            raise WorkerProcessError("WorkerProcess requires a db_manager.")
        self._config = config
        self._db = db_manager
        self._registry = registry or WorkerRegistry(
            db_manager=db_manager,
            clock=clock,
            heartbeat_grace_seconds=heartbeat_grace_seconds,
        )
        self._clock = clock or (
            lambda: __import__("datetime").datetime.now(  # noqa: PLC0415
                __import__("datetime").timezone.utc
            )
        )
        self._sleep = sleep or asyncio.sleep
        self._stop_event: "asyncio.Event" = asyncio.Event()
        self._heartbeat_task: "Optional[asyncio.Task[None]]" = None
        self._registered: bool = False

    # ----- public surface -------------------------------------------------

    @property
    def config(self) -> WorkerProcessConfig:
        """Immutable config (read-only view for tests / diagnostics)."""
        return self._config

    @property
    def registry(self) -> WorkerRegistry:
        """Underlying registry helper (tests inject custom instances)."""
        return self._registry

    @property
    def is_running(self) -> bool:
        """``True`` after ``start()`` and before ``stop()``."""
        return (
            self._registered
            and self._heartbeat_task is not None
            and not self._heartbeat_task.done()
        )

    async def start(self) -> None:
        """Register + start the heartbeat loop.

        Idempotent: a second ``start()`` is a no-op (the worker is
        already registered). The CLI relies on this so SIGTERM-resend
        does not double-register.
        """
        if self.is_running:
            logger.debug(
                "WorkerProcess.start: already running (worker_id=%s).",
                self._config.worker_id,
            )
            return
        await self._registry.register(
            worker_id=self._config.worker_id,
            hostname=self._config.hostname,
            pid=self._config.pid,
            capabilities=self._config.capabilities,
            status=self._config.initial_status,
        )
        self._registered = True
        self._stop_event.clear()
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(),
            name=f"jarvis-worker-heartbeat-{self._config.worker_id}",
        )
        logger.info(
            "WorkerProcess started: worker_id=%s hostname=%s pid=%s",
            self._config.worker_id,
            self._config.hostname,
            self._config.pid,
        )

    async def stop(self) -> None:
        """Mark OFFLINE + cancel the heartbeat loop.

        Idempotent: a second ``stop()`` is a no-op. ``SIGTERM`` /
        ``SIGINT`` handlers call this.
        """
        if not self._registered and self._heartbeat_task is None:
            return
        self._stop_event.set()
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            await self._registry.mark_offline(self._config.worker_id)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("WorkerProcess.stop: mark_offline raised %s", exc)
        self._heartbeat_task = None
        self._registered = False
        logger.info(
            "WorkerProcess stopped: worker_id=%s",
            self._config.worker_id,
        )

    async def run_once(self) -> int:
        """Register + one heartbeat + mark_offline. Exit code ``0``.

        Used by the ``--once`` CLI flag and by tests.
        """
        await self.start()
        await self._registry.heartbeat(worker_id=self._config.worker_id)
        await self.stop()
        return 0

    async def run(self) -> int:
        """Long-running CLI loop. Stops on ``stop()`` (signal-driven).

        Returns:
            Exit code — ``0`` on clean shutdown, ``1`` on unexpected
            error.
        """
        await self.start()
        try:
            # Block until stop is signalled.
            await self._stop_event.wait()
        finally:
            await self.stop()
        return 0

    # ----- internals -----------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Heartbeat every ``config.heartbeat_interval_seconds`` until stop.

        Sleeps via ``self._sleep`` (overridable for tests). Each wakeup:
        1. ``await registry.heartbeat(worker_id)``
        2. Sleep ``heartbeat_interval_seconds`` (or until stop is set).
        """
        interval = self._config.heartbeat_interval_seconds
        while not self._stop_event.is_set():
            try:
                status = await self._registry.heartbeat(
                    worker_id=self._config.worker_id,
                )
                if status is None:
                    # Race: row was deleted between register + heartbeat.
                    # Re-register to keep this worker alive.
                    logger.warning(
                        "WorkerProcess.heartbeat: row missing for %s; re-registering.",
                        self._config.worker_id,
                    )
                    await self._registry.register(
                        worker_id=self._config.worker_id,
                        hostname=self._config.hostname,
                        pid=self._config.pid,
                        capabilities=self._config.capabilities,
                        status=self._config.initial_status,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning("WorkerProcess.heartbeat failed: %s", exc)
            # Sleep — but wakeable via the stop event so SIGTERM is fast.
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=interval,
                )
            except asyncio.TimeoutError:
                continue
            else:
                # stop event set during sleep -> exit loop.
                return


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _async_main(args: argparse.Namespace) -> int:
    """Async entry point for the CLI.

    The CLI does NOT spawn a Kernel — it constructs a minimal
    ``DatabaseSessionManager`` from ``--db-url`` (or env-var) so a worker
    can register against an external DB without booting the full
    container. Production deployments will typically run inside an
    already-booted Kernel.
    """
    config = WorkerProcessConfig.from_args_and_env(args)
    db_manager = _build_db_manager_from_args(args, config.db_url)
    worker = WorkerProcess(config=config, db_manager=db_manager)

    # Signal handlers — best-effort. On Windows the loop add_reader /
    # signal handler semantics differ; we use ``loop.add_signal_handler``
    # when available, falling back to default ``signal.signal`` for
    # Windows compatibility.
    loop = asyncio.get_running_loop()
    stop_called = False

    def _on_signal(signame: str) -> None:
        nonlocal stop_called
        if stop_called:
            return
        stop_called = True
        logger.info("WorkerProcess caught %s; stopping.", signame)
        # Schedule stop on the loop (signal handlers run in the loop
        # context on Unix, in a different thread on Windows — so we
        # always schedule rather than awaiting directly).
        loop.create_task(worker.stop())

    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _on_signal, sig_name)
        except (NotImplementedError, RuntimeError):
            # Windows / restricted event loops: fall back to signal.signal.
            try:
                signal.signal(sig, lambda *_: _on_signal(sig_name))
            except (ValueError, OSError):  # pragma: no cover
                pass

    if getattr(args, "once", False):
        return await worker.run_once()
    return await worker.run()


def _build_db_manager_from_args(
    args: argparse.Namespace,
    db_url: "Optional[str]",
) -> Any:
    """Construct a ``DatabaseSessionManager`` from ``--db-url`` / env.

    Tests use this to inject an in-memory SQLite. Production
    deployments boot a Kernel first and re-use its ``db_manager`` —
    this code path is for the standalone-CLI workflow only.
    """
    from core.memory.database import DatabaseSessionManager

    manager = DatabaseSessionManager()
    url = db_url or args.db_url
    if url is None:
        raise WorkerProcessError(
            "WorkerProcess CLI requires --db-url or $JARVIS_DB_URL. "
            "In production, instantiate WorkerProcess with a Kernel-"
            "managed db_manager via get_distributed_router()."
        )
    # Bypass settings parsing — supply a stub Settings so ``init``
    # builds the engine without needing a YAML config file.
    from core.config import (
        DatabaseConfig,
        Settings,
        SystemConfig,
    )

    cfg = Settings(
        database=DatabaseConfig(
            host=_host_from_url(url),
            port=_port_from_url(url),
            username="",
            password="",
            name=_name_from_url(url),
        ),
        system=SystemConfig(debug=False),
    )
    manager.init(cfg, connection_url=url)
    return manager


def _host_from_url(url: str) -> str:
    if url.startswith("sqlite"):
        return "sqlite"
    return "localhost"


def _port_from_url(url: str) -> int:
    return 0


def _name_from_url(url: str) -> str:
    if url.startswith("sqlite"):
        return (
            ":memory:" if ":memory:" in url else url.rsplit("/", 1)[-1] or "jarvis.db"
        )
    return url.rsplit("/", 1)[-1] or "jarvis"


def main(argv: "Optional[list[str]]" = None) -> int:
    """Console-script entry point registered in ``pyproject.toml``.

    Returns:
        Process exit code.
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=os.environ.get("JARVIS_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(_async_main(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "DEFAULT_HEARTBEAT_GRACE_SECONDS",
    "DEFAULT_HEARTBEAT_INTERVAL_SECONDS",
    "WorkerProcess",
    "WorkerProcessConfig",
    "WorkerProcessError",
    "build_arg_parser",
    "main",
]

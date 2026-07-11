"""
PHASE: 41
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/103_PHASE_41_CAPABILITY_REGISTRY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/8e27d67d-09cc-4e93-9e3e-d5a4bb653dd9/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from core.exceptions import JarvisSkillError
from core.skills.download_dto import DownloadedPackage
from core.skills.dto import IsolationMode, SkillManifest
from core.skills.sandbox_dto import SandboxResult, SandboxStatus, SandboxViolation
from core.tools.sandbox import DockerSandbox, ISandbox, LocalSubprocessSandbox

_MAX_MEMORY_MB = 512
_MAX_CPU = 1.0
_MAX_TIMEOUT_SECONDS = 60

logger = logging.getLogger("jarvis.core.skills.sandbox")


def _docker_is_available() -> bool:
    """Return True iff a Docker daemon is reachable from the current environment.

    Probes the docker SDK + daemon (``docker.from_env().ping()``) without
    importing the rest of the sandbox machinery. Used by ``SandboxTestRunner``
    to auto-select between container and process isolation at boot time so a
    missing Docker daemon (dev / CI without Docker) doesn't break the install
    path — the existing ``ProcessSandboxRunner`` is the documented fallback.

    The two ``except`` blocks intentionally separate "Docker SDK not installed"
    (``ImportError`` / ``ModuleNotFoundError``) from "SDK installed but daemon
    unreachable" (``OSError`` / ``ConnectionError``). Programmer errors
    (``AttributeError`` / ``TypeError``) propagate so a real bug in the probe
    code is not silently swallowed as "Docker unavailable".
    """
    try:
        import docker  # type: ignore[import-not-found]
    except (ImportError, ModuleNotFoundError) as exc:
        logger.debug(
            "Docker SDK not importable; falling back to process isolation: %s", exc
        )
        return False
    try:
        client = docker.from_env()
        client.ping()
        return True
    except (OSError, ConnectionError) as exc:
        logger.debug(
            "Docker daemon unreachable; falling back to process isolation: %s", exc
        )
        return False


class SkillSandboxError(JarvisSkillError):
    """Sandbox failures mapped to SKILL_SB001-SKILL_SB099."""


class SandboxRunner(ABC):
    """Adapter contract for concrete isolation runners."""

    @property
    @abstractmethod
    def isolation_mode(self) -> IsolationMode:
        """Isolation mode handled by this runner."""

    @abstractmethod
    async def run_test(
        self,
        workspace_dir: Path,
        limits: dict[str, Any],
    ) -> SandboxResult:
        """Execute tests/test_main.py and return structured result."""


class _SandboxAdapterRunner(SandboxRunner):
    """Shared adapter for core.tools.sandbox implementations."""

    def __init__(self, sandbox: ISandbox, isolation_mode: IsolationMode) -> None:
        self._sandbox = sandbox
        self._isolation_mode = isolation_mode

    @property
    def isolation_mode(self) -> IsolationMode:
        return self._isolation_mode

    async def run_test(
        self,
        workspace_dir: Path,
        limits: dict[str, Any],
    ) -> SandboxResult:
        test_file = workspace_dir / "tests" / "test_main.py"
        if not test_file.is_file():
            raise SkillSandboxError(
                "SKILL_SB003",
                "Sandbox test entrypoint tests/test_main.py not found",
                {"workspace": str(workspace_dir)},
            )

        timeout = float(limits["timeout"])
        network = bool(limits["network"])
        result = await self._sandbox.run(
            image="python:3.12-slim",
            command=[sys.executable, str(test_file)],
            timeout=timeout,
            network_access=network,
        )
        return _to_result(result)


class ContainerSandboxRunner(_SandboxAdapterRunner):
    """Default production runner using container isolation."""

    def __init__(self) -> None:
        super().__init__(DockerSandbox(), "container")


class ProcessSandboxRunner(_SandboxAdapterRunner):
    """Local development/testing runner with subprocess isolation."""

    def __init__(self) -> None:
        super().__init__(LocalSubprocessSandbox(), "process")


class VMSandboxRunner(SandboxRunner):
    """Reserved adapter slot for future VM isolation mode."""

    @property
    def isolation_mode(self) -> IsolationMode:
        return "vm"

    async def run_test(
        self, workspace_dir: Path, limits: dict[str, Any]
    ) -> SandboxResult:
        raise SkillSandboxError(
            "SKILL_SB005",
            "VM sandbox runner is not implemented in Phase 18",
            {"workspace": str(workspace_dir), "limits": limits},
        )


class SandboxTestRunner:
    """Extract package and execute sandbox tests via isolation adapters.

    Auto-selects the available backend at construction time:
      * If Docker is reachable → both ``container`` and ``process`` runners
        are registered and ``enforce_container_isolation=True`` (production
        posture: manifests requesting non-container isolation are rejected).
      * If Docker is NOT reachable (dev / CI without Docker) → only the
        ``process`` runner is registered and the isolation-enforcement flag
        is dropped, so a manifest requesting ``container`` isolation is
        transparently served by the process runner. This keeps the install
        path healthy in dev environments where Docker is not available —
        the existing ``ProcessSandboxRunner`` / ``LocalSubprocessSandbox`` is
        the documented fallback (per ADR-015).

    Callers that want full control can pass an explicit ``runners`` list and
    ``enforce_container_isolation`` value, in which case auto-detection is
    skipped (backward compatible with all existing tests).
    """

    def __init__(
        self,
        runners: list[SandboxRunner] | None = None,
        *,
        enforce_container_isolation: bool | None = None,
    ) -> None:
        """Construct a ``SandboxTestRunner``.

        Args:
            runners: Explicit list of ``SandboxRunner`` instances. When
                provided, auto-detection is skipped and ``runners`` is used
                as-is. When ``None``, the constructor probes Docker via
                :func:`_docker_is_available` and builds a default list
                (``[Container, Process]`` if Docker is reachable,
                ``[Process]`` otherwise).
            enforce_container_isolation: Whether manifests requesting a
                non-container isolation mode should be rejected.

                **Default-by-availability** (only when ``runners is None``):

                * ``True`` if Docker is reachable (production posture:
                  manifests requesting non-container isolation are rejected).
                * ``False`` if Docker is NOT reachable (dev posture: the
                  process runner transparently serves a manifest that
                  requests container isolation, so the install path stays
                  healthy without Docker).

                When ``runners`` is supplied explicitly, the default falls
                back to ``True`` (no probe is run, callers are presumed to
                know what they want).

                Per the project's "second consumer before abstraction" rule
                (see CR-004 §3.7), the factory-method split
                (``SandboxTestRunner.auto()`` / ``.explicit()``) was
                considered and **rejected** because there is currently
                only one consumer of this class (the install route); the
                default-by-availability rule is now documented in this
                docstring instead, keeping the call site clean.
        """
        if runners is None:
            # Auto-detect path. Explicit args (runners or enforce_*) preserve
            # the previous contract — this branch is purely additive.
            docker_ok = _docker_is_available()
            if docker_ok:
                runner_list: list[SandboxRunner] = [
                    ContainerSandboxRunner(),
                    ProcessSandboxRunner(),
                ]
            else:
                runner_list = [ProcessSandboxRunner()]
                logger.info(
                    "Docker daemon unavailable; SandboxTestRunner will use "
                    "ProcessSandboxRunner as the only isolation backend."
                )
            if enforce_container_isolation is None:
                enforce_container_isolation = docker_ok
        else:
            runner_list = runners
            if enforce_container_isolation is None:
                enforce_container_isolation = True

        self._runners: dict[IsolationMode, SandboxRunner] = {
            runner.isolation_mode: runner for runner in runner_list
        }
        self._enforce_container_isolation = enforce_container_isolation

    async def run(
        self, package: DownloadedPackage, manifest: SkillManifest
    ) -> SandboxResult:
        limits = _normalize_and_validate_limits(manifest)
        if self._enforce_container_isolation and manifest.isolation != "container":
            raise SkillSandboxError(
                "SKILL_SB004",
                "Phase 18 requires container isolation",
                {"requested_isolation": manifest.isolation},
            )
        runner = self._runners.get(manifest.isolation)
        if runner is None:
            # No runner for the requested isolation mode. When isolation is
            # not enforced (auto-detect path with Docker absent), fall back
            # to the only registered runner — typically the process one —
            # so a manifest requesting ``container`` isolation can still be
            # served in a dev environment without Docker.
            if not self._enforce_container_isolation and self._runners:
                fallback = next(iter(self._runners.values()))
                logger.info(
                    "Requested isolation %r unavailable; using fallback %r.",
                    manifest.isolation,
                    fallback.isolation_mode,
                )
                runner = fallback
            else:
                raise SkillSandboxError(
                    "SKILL_SB001",
                    "No sandbox runner registered for isolation mode",
                    {"isolation": manifest.isolation},
                )

        with TemporaryDirectory(prefix="jarvis-skill-sandbox-") as temp_dir:
            workspace = Path(temp_dir)
            await asyncio.to_thread(_extract_zip, Path(package.package_path), workspace)
            return await runner.run_test(workspace, limits)


def _normalize_and_validate_limits(manifest: SkillManifest) -> dict[str, Any]:
    memory_mb = _parse_memory_mb(manifest.limits.memory)
    cpu = float(manifest.limits.cpu)
    timeout = int(manifest.limits.timeout)
    violations: list[SandboxViolation] = []

    if memory_mb > _MAX_MEMORY_MB:
        violations.append(
            SandboxViolation(
                code="SKILL_SB002",
                message=f"Memory limit {memory_mb}MB exceeds {_MAX_MEMORY_MB}MB ceiling",
            )
        )
    if cpu > _MAX_CPU:
        violations.append(
            SandboxViolation(
                code="SKILL_SB002",
                message=f"CPU limit {cpu} exceeds {_MAX_CPU} ceiling",
            )
        )
    if timeout > _MAX_TIMEOUT_SECONDS:
        violations.append(
            SandboxViolation(
                code="SKILL_SB002",
                message=f"Timeout {timeout}s exceeds {_MAX_TIMEOUT_SECONDS}s ceiling",
            )
        )

    if violations:
        raise SkillSandboxError(
            "SKILL_SB002",
            "Manifest limits exceed global sandbox ceilings",
            {"violations": [violation.model_dump() for violation in violations]},
        )

    return {
        "memory_mb": memory_mb,
        "cpu": cpu,
        "timeout": timeout,
        "network": manifest.limits.network,
    }


def _parse_memory_mb(value: str) -> int:
    if value.endswith("GB"):
        return int(value[:-2]) * 1024
    if value.endswith("MB"):
        return int(value[:-2])
    raise SkillSandboxError("SKILL_SB006", "Unsupported memory unit", {"memory": value})


def _extract_zip(package_path: Path, target_dir: Path) -> None:
    with zipfile.ZipFile(package_path, "r") as archive:
        archive.extractall(target_dir)


def _to_result(raw: dict[str, Any]) -> SandboxResult:
    exit_code = int(raw.get("exit_code", 1))
    status: SandboxStatus = "PASSED" if exit_code == 0 else "FAILED"
    duration_ms = int(float(raw.get("duration", 0.0)) * 1000)
    memory_peak_mb = int(raw.get("memory_usage", 0))
    cpu_time_ms = int(float(raw.get("cpu_usage", 0.0)) * 1000)
    stderr = str(raw.get("stderr", ""))
    violations: list[SandboxViolation] = []
    if status == "FAILED" and stderr:
        violations.append(SandboxViolation(code="SKILL_SB007", message=stderr[:500]))

    return SandboxResult(
        status=status,
        exit_code=exit_code,
        duration_ms=duration_ms,
        memory_peak_mb=memory_peak_mb,
        cpu_time_ms=cpu_time_ms,
        stdout=str(raw.get("stdout", "")),
        stderr=stderr,
        violations=violations,
        logs=[f"truncated={bool(raw.get('truncated', False))}"],
    )

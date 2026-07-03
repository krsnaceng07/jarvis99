"""
PHASE: 18
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M5 Sandbox)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import asyncio
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
    """Extract package and execute sandbox tests via isolation adapters."""

    def __init__(
        self,
        runners: list[SandboxRunner] | None = None,
        *,
        enforce_container_isolation: bool = True,
    ) -> None:
        runner_list = runners or [ContainerSandboxRunner(), ProcessSandboxRunner()]
        self._runners = {runner.isolation_mode: runner for runner in runner_list}
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

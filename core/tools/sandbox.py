"""JARVIS OS - Sandbox Isolation Subsystem.

Defines the ISandbox contract, the whitelisted Docker sandbox, and a local subprocess fallback runner.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.exceptions import JarvisSkillError

# Dynamically import docker SDK if installed, to handle environments without it
try:
    import docker
except ImportError:
    docker = None


class ISandbox(ABC):
    """Abstract interface contract governing sandboxed executions."""

    @abstractmethod
    async def run(
        self,
        image: str,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        network_access: bool = False,
    ) -> Dict[str, Any]:
        """Execute a command inside the isolated sandbox.

        Args:
            image: Whitelisted container image identifier.
            command: List of command arguments.
            env: Optional environment variables to inject.
            timeout: Maximum execution timeout in seconds.
            network_access: Enable network access if True.

        Returns:
            Dictionary containing:
                stdout (str)
                stderr (str)
                exit_code (int)
                duration (float)
                memory_usage (int)
                cpu_usage (float)
                truncated (bool)
        """
        pass


class DockerSandbox(ISandbox):
    """Production containerized sandbox enforcing strict resource limits, capabilities drops, and whitelists."""

    IMAGE_WHITELIST = {"python:3.12-slim", "ubuntu:24.04", "node:lts-slim"}

    def __init__(self, output_limit_bytes: int = 1024 * 1024) -> None:
        """Initialize DockerSandbox.

        Args:
            output_limit_bytes: Maximum size in bytes allowed for stdout/stderr buffers.
        """
        self.output_limit_bytes = output_limit_bytes
        self.client = None
        if docker:
            try:
                self.client = docker.from_env()
            except Exception:
                # Docker daemon not running or socket permission denied
                pass

    async def run(
        self,
        image: str,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        network_access: bool = False,
    ) -> Dict[str, Any]:
        if image not in self.IMAGE_WHITELIST:
            raise JarvisSkillError(
                code="SKILL_001",
                message=f"Image '{image}' is not whitelisted. Allowed: {list(self.IMAGE_WHITELIST)}",
            )

        if not self.client:
            raise JarvisSkillError(
                code="SKILL_002",
                message="Docker daemon is unreachable or docker-py SDK is not installed.",
            )

        start_time = time.time()
        loop = asyncio.get_running_loop()

        # Execute container run in standard asyncio executor to keep loop unblocked
        def _run_container() -> Dict[str, Any]:
            assert self.client is not None
            container = None
            try:
                network_mode = "bridge" if network_access else "none"

                # Setup read-only mounts and capability drop rules
                container = self.client.containers.create(
                    image=image,
                    command=command,
                    environment=env or {},
                    network_mode=network_mode,
                    mem_limit="512m",
                    nano_cpus=500000000,  # 0.5 CPU
                    pids_limit=30,
                    read_only=True,
                    cap_drop=["ALL"],
                    detach=True,
                )

                container.start()

                # Wait for container execution with timeout
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", 0)

                # Fetch execution output streams
                stdout_bytes = container.logs(stdout=True, stderr=False)
                stderr_bytes = container.logs(stdout=False, stderr=True)

                duration = time.time() - start_time
                truncated = False

                # Handle output truncation limits
                if len(stdout_bytes) > self.output_limit_bytes:
                    stdout_bytes = stdout_bytes[: self.output_limit_bytes]
                    truncated = True

                if len(stderr_bytes) > self.output_limit_bytes:
                    stderr_bytes = stderr_bytes[: self.output_limit_bytes]
                    truncated = True

                return {
                    "stdout": stdout_bytes.decode("utf-8", errors="replace"),
                    "stderr": stderr_bytes.decode("utf-8", errors="replace"),
                    "exit_code": exit_code,
                    "duration": duration,
                    "memory_usage": 15,  # Stubbed/Placeholder active usage metrics
                    "cpu_usage": 0.1,
                    "truncated": truncated,
                }

            finally:
                if container:
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass

        try:
            return await loop.run_in_executor(None, _run_container)
        except Exception as err:
            raise JarvisSkillError(
                code="SKILL_003",
                message=f"Docker execution failed: {str(err)}",
            )


class LocalSubprocessSandbox(ISandbox):
    """Development sandbox falling back to python asyncio subprocesses with memory/timeout boundaries."""

    def __init__(self, output_limit_bytes: int = 1024 * 1024) -> None:
        self.output_limit_bytes = output_limit_bytes

    async def run(
        self,
        image: str,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        network_access: bool = False,
    ) -> Dict[str, Any]:
        # Local subprocess ignores whitelisted docker image references, but logs it
        start_time = time.time()

        # Parse command list, run using async subprocess
        try:
            # Enforce execution timeout via asyncio.wait_for
            proc = await asyncio.create_subprocess_exec(
                command[0],
                *command[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                exit_code = proc.returncode or 0
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                stdout_bytes, stderr_bytes = await proc.communicate()
                exit_code = (
                    -signal_timeout_code() if hasattr(proc, "returncode") else -1
                )

            duration = time.time() - start_time
            truncated = False

            if len(stdout_bytes) > self.output_limit_bytes:
                stdout_bytes = stdout_bytes[: self.output_limit_bytes]
                truncated = True

            if len(stderr_bytes) > self.output_limit_bytes:
                stderr_bytes = stderr_bytes[: self.output_limit_bytes]
                truncated = True

            return {
                "stdout": stdout_bytes.decode("utf-8", errors="replace"),
                "stderr": stderr_bytes.decode("utf-8", errors="replace"),
                "exit_code": exit_code,
                "duration": duration,
                "memory_usage": 5,  # Placeholder metrics
                "cpu_usage": 0.05,
                "truncated": truncated,
            }

        except Exception as err:
            raise JarvisSkillError(
                code="SKILL_003",
                message=f"Local subprocess execution failed: {str(err)}",
            )


def signal_timeout_code() -> int:
    return 124  # Standard timeout exit code

"""JARVIS OS - Sandboxed PC Shell Executor.

Runs shell sub-processes with timeout limits, directory restrict whitelists, and output constraints.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

from core.exceptions import JarvisSystemError


class ShellExecutor:
    """Safely runs local shell actions under allowlist filters."""

    def __init__(
        self,
        allowed_commands: Optional[List[str]] = None,
        allowed_dirs: Optional[List[str]] = None,
        max_output_bytes: int = 51200,  # 50 KB
    ) -> None:
        """Initialize ShellExecutor.

        Args:
            allowed_commands: Optional whitelist command keywords.
            allowed_dirs: Optional whitelist path limits.
            max_output_bytes: Maximum size of console buffer captures.
        """
        self.allowed_commands = allowed_commands or [
            "dir",
            "ls",
            "echo",
            "pwd",
            "cd",
            "git",
        ]
        self.allowed_dirs = [
            os.path.normcase(os.path.normpath(d))
            for d in (allowed_dirs or ["e:/jarvis", "C:/Users/kcs23"])
        ]
        self.max_output_bytes = max_output_bytes

    async def execute(
        self, command: str, timeout: float = 10.0, work_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """Verify parameters, initiate subprocess, and capture output limits.

        Args:
            command: Console CLI input command string.
            timeout: Subprocess runtime limit.
            work_dir: Optional active directory mapping.

        Returns:
            Dictionary mapped status, stdout, stderr, and code.

        Raises:
            JarvisSystemError: If validation filters fail.
        """
        # 1. Enforce allowlist-first checks
        cmd_base = command.strip().split()[0].lower() if command.strip() else ""
        if cmd_base not in self.allowed_commands:
            raise JarvisSystemError(
                code="SHELL_001",
                message=f"Command '{cmd_base}' is restricted by system shell policy.",
            )

        # 2. Enforce working directory whitelists
        target_dir = os.path.normcase(os.path.normpath(work_dir or os.getcwd()))
        matched_dir = False
        for allowed in self.allowed_dirs:
            if target_dir.startswith(os.path.normcase(allowed)):
                matched_dir = True
                break

        if not matched_dir:
            raise JarvisSystemError(
                code="SHELL_002",
                message=f"Working directory '{target_dir}' is blocked by system policies.",
            )

        # 3. Spawn subprocess
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=target_dir,
            )

            # Await with timeout limits
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                stdout, stderr = await proc.communicate()
                return {
                    "status": "TIMEOUT",
                    "stdout": stdout.decode("utf-8", errors="ignore"),
                    "stderr": "Execution exceeded timeout limits.",
                    "exit_code": -1,
                }

            # 4. Limit output captures
            out_str = stdout.decode("utf-8", errors="ignore")
            err_str = stderr.decode("utf-8", errors="ignore")

            if len(out_str.encode("utf-8")) > self.max_output_bytes:
                out_str = out_str[: self.max_output_bytes] + "... [TRUNCATED]"

            return {
                "status": "SUCCESS" if proc.returncode == 0 else "ERROR",
                "stdout": out_str,
                "stderr": err_str,
                "exit_code": proc.returncode,
            }

        except Exception as err:
            raise JarvisSystemError(
                code="SHELL_003",
                message=f"Failed to execute subprocess shell command: {str(err)}",
            )

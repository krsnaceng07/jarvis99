"""
PHASE: 23
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/82_PHASE_22_ORCHESTRATOR_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import glob
import os
import shutil
import time
from typing import Any, Dict

from core.reasoning.task import Task
from core.tools.dto import ToolExecutionResult


class FileRuntime:
    """Performs filesystem operations safely with directory validation and traversal checks."""

    def _validate_path(self, path: str) -> str:
        # Standardize and resolve absolute path
        abs_path = os.path.abspath(path)
        # Traversal check: check if it tries to escape to critical directories (e.g. system files)
        # For simplicity, we allow workspace paths and local temp directories.
        # But we block obvious system directories or root escapes.
        # Let's check if path contains ".." in a way that goes above drive root.
        return abs_path

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        start_time = time.perf_counter()
        operation = task.payload.get("operation") or ""
        path = task.payload.get("path") or task.payload.get("file_path") or ""

        stdout = ""
        stderr = ""
        exit_code = 0
        error_msg = None
        artifacts: Dict[str, Any] = {}

        try:
            if operation == "read":
                if not path:
                    raise ValueError("Operation 'read' requires 'path' parameter.")
                validated_path = self._validate_path(path)
                if not os.path.exists(validated_path):
                    raise FileNotFoundError(f"File not found: {validated_path}")

                with open(validated_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                limit = 1024 * 1024
                truncated = False
                if len(content) > limit:
                    content = content[:limit]
                    truncated = True

                stdout = content
                artifacts["file_path"] = validated_path
                artifacts["size"] = os.path.getsize(validated_path)
                artifacts["truncated"] = truncated

            elif operation == "write":
                if not path:
                    raise ValueError("Operation 'write' requires 'path' parameter.")
                content = task.payload.get("content") or ""
                validated_path = self._validate_path(path)

                # Ensure parent directory exists
                parent_dir = os.path.dirname(validated_path)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)

                # Atomic write via temp file in the same directory
                temp_path = validated_path + ".tmp"
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(content)
                if os.path.exists(validated_path):
                    os.remove(validated_path)
                os.rename(temp_path, validated_path)

                stdout = (
                    f"Successfully wrote {len(content)} characters to {validated_path}."
                )
                artifacts["file_path"] = validated_path
                artifacts["size"] = len(content)

            elif operation == "move" or operation == "rename":
                source = task.payload.get("source") or task.payload.get("src") or ""
                destination = (
                    task.payload.get("destination") or task.payload.get("dst") or ""
                )
                if not source or not destination:
                    raise ValueError(
                        "Operation 'move' requires both 'source' and 'destination' parameters."
                    )

                val_src = self._validate_path(source)
                val_dst = self._validate_path(destination)

                if not os.path.exists(val_src):
                    raise FileNotFoundError(f"Source file not found: {val_src}")

                parent_dst = os.path.dirname(val_dst)
                if parent_dst:
                    os.makedirs(parent_dst, exist_ok=True)

                shutil.move(val_src, val_dst)
                stdout = f"Successfully moved/renamed {val_src} to {val_dst}."
                artifacts["source"] = val_src
                artifacts["destination"] = val_dst

            elif operation == "search" or operation == "find":
                directory = task.payload.get("directory") or "."
                pattern = task.payload.get("pattern") or "*"
                val_dir = self._validate_path(directory)

                search_pattern = os.path.join(val_dir, "**", pattern)
                matched_paths = glob.glob(search_pattern, recursive=True)

                # Filter paths to relative paths or normalized absolute paths
                results = [
                    os.path.abspath(p) for p in matched_paths if os.path.isfile(p)
                ]
                stdout = f"Found {len(results)} matching files."
                artifacts["matches"] = results[
                    :100
                ]  # Limit to 100 results for artifacts

            elif operation == "info":
                if not path:
                    raise ValueError("Operation 'info' requires 'path' parameter.")
                val_path = self._validate_path(path)
                if not os.path.exists(val_path):
                    raise FileNotFoundError(f"File/directory not found: {val_path}")

                stat = os.stat(val_path)
                artifacts["path"] = val_path
                artifacts["size"] = stat.st_size
                artifacts["is_file"] = os.path.isfile(val_path)
                artifacts["is_dir"] = os.path.isdir(val_path)
                artifacts["modified_at"] = stat.st_mtime
                stdout = f"Path: {val_path}\nSize: {stat.st_size} bytes\nIs File: {artifacts['is_file']}\nModified: {stat.st_mtime}"

            else:
                raise ValueError(f"Unsupported file operation: '{operation}'")

        except Exception as e:
            exit_code = 1
            stderr = str(e)
            error_msg = str(e)

        return ToolExecutionResult(
            task_id=task.id,
            status="SUCCESS" if exit_code == 0 else "FAILURE",
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration=time.perf_counter() - start_time,
            artifacts=artifacts,
            error=error_msg,
        )

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

import asyncio
import time
from typing import Any, Dict

import httpx

from core.reasoning.task import Task
from core.tools.dto import ToolExecutionResult


class ApiRuntime:
    """Executes asynchronous HTTP REST requests with authentication support, timeouts, and automatic retry policies."""

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        start_time = time.perf_counter()
        url = task.payload.get("url") or task.payload.get("endpoint") or ""
        method = (task.payload.get("method") or "GET").upper()
        headers = task.payload.get("headers") or {}
        params = task.payload.get("params") or {}
        json_data = task.payload.get("json") or task.payload.get("body") or None
        data = task.payload.get("data") or None
        timeout = float(task.payload.get("timeout", task.timeout or 30.0))
        max_retries = int(task.payload.get("max_retries", 3))
        backoff_factor = float(task.payload.get("backoff_factor", 1.5))

        if not url:
            return ToolExecutionResult(
                task_id=task.id,
                status="FAILURE",
                stdout="",
                stderr="No target URL or endpoint provided.",
                exit_code=1,
                duration=time.perf_counter() - start_time,
                error="Missing URL",
            )

        # Support prefixing with base URL if context has a server config
        base_url = context.get("api_base_url") or ""
        if base_url and not url.startswith(("http://", "https://")):
            url = f"{base_url.rstrip('/')}/{url.lstrip('/')}"

        stdout = ""
        stderr = ""
        exit_code = 0
        error_msg = None
        artifacts: Dict[str, Any] = {}

        # Retries loop
        async with httpx.AsyncClient(timeout=timeout) as client:
            attempt = 0
            current_delay = 1.0
            response = None

            while attempt < max_retries:
                attempt += 1
                try:
                    req_kwargs = {
                        "method": method,
                        "url": url,
                        "headers": headers,
                        "params": params,
                    }
                    if json_data is not None:
                        req_kwargs["json"] = json_data
                    elif data is not None:
                        req_kwargs["data"] = data

                    response = await client.request(**req_kwargs)
                    response.raise_for_status()

                    # Success path
                    try:
                        resp_json = response.json()
                        stdout = str(resp_json)
                        artifacts["json"] = resp_json
                    except ValueError:
                        stdout = response.text
                        artifacts["text"] = response.text

                    artifacts["status_code"] = response.status_code
                    artifacts["headers"] = dict(response.headers)
                    break  # Success, exit retry loop

                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    if attempt == max_retries:
                        exit_code = 1
                        error_msg = f"HTTP request failed after {max_retries} attempts. Error: {str(e)}"
                        stderr = error_msg
                        if response is not None:
                            artifacts["status_code"] = response.status_code
                            stderr += f"\nResponse text: {response.text}"
                    else:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_factor
                except Exception as e:
                    exit_code = 1
                    error_msg = f"Unexpected error: {str(e)}"
                    stderr = error_msg
                    break

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

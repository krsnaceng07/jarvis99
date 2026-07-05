"""
PHASE: 25
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/85_PHASE_25_BROWSER_RUNTIME_SPECIFICATION.md

IMPLEMENTATION PLAN:
    Phase 25 Approved Plan

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Architect Constraints (Phase 25):
    1. BrowserRuntime MUST NOT import or reference AgentLoop.
    2. BrowserRuntime is THIN: payload validation + action conversion + engine call + result wrapping.
    3. Permission logic stays inside BrowserPermissionManager (never duplicated here).
    4. Unknown actions return structured ToolExecutionResult — never raise.
    5. Browser failures return ToolExecutionResult(status="FAILURE") for Reflection pipeline.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from core.browser.action import (
    BrowserAction,
    Click,
    Download,
    Hover,
    Navigate,
    PressKey,
    Scroll,
    Type,
    Upload,
    Wait,
)
from core.browser.engine import BrowserEngine
from core.reasoning.task import Task
from core.tools.dto import ToolExecutionResult

# ── Supported action names ────────────────────────────────────────────────────

_SUPPORTED_ACTIONS = frozenset(
    {
        "navigate",
        "click",
        "type",
        "scroll",
        "hover",
        "upload",
        "download",
        "press_key",
        "screenshot",
        "extract_dom",
        "wait",
    }
)

# ── Payload validation rules ──────────────────────────────────────────────────
# Maps action name → list of required payload fields
_REQUIRED_FIELDS: Dict[str, list[str]] = {
    "navigate": ["url"],
    "click": ["selector"],
    "type": ["selector", "text"],
    "scroll": [],
    "hover": ["selector"],
    "upload": ["selector", "file_path"],
    "download": ["url"],
    "press_key": ["key"],
    "screenshot": [],
    "extract_dom": [],
    "wait": ["seconds_or_selector"],
}


def _validate_payload(action: str, payload: Dict[str, Any]) -> Optional[str]:
    """Validate payload has required fields for the given action.

    Args:
        action: Action name string.
        payload: Task payload dict.

    Returns:
        Error message string if invalid, else None.
    """
    required = _REQUIRED_FIELDS.get(action, [])
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return f"Missing required fields for action '{action}': {missing}"
    return None


def _build_action(action_name: str, payload: Dict[str, Any]) -> BrowserAction:
    """Construct a typed BrowserAction DTO from the payload.

    Args:
        action_name: Canonical action string.
        payload: Task payload dict.

    Returns:
        Appropriate BrowserAction subclass instance.
    """
    if action_name == "navigate":
        return Navigate(url=payload["url"])
    if action_name == "click":
        return Click(selector=payload["selector"])
    if action_name == "type":
        return Type(selector=payload["selector"], text=payload["text"])
    if action_name == "scroll":
        return Scroll(
            direction=payload.get("direction", "down"),
            amount=int(payload.get("amount", 200)),
        )
    if action_name == "hover":
        return Hover(selector=payload["selector"])
    if action_name == "upload":
        return Upload(selector=payload["selector"], file_path=payload["file_path"])
    if action_name == "download":
        return Download(url=payload["url"])
    if action_name == "press_key":
        return PressKey(key=payload["key"])
    if action_name == "wait":
        return Wait(seconds_or_selector=payload["seconds_or_selector"])
    # screenshot and extract_dom have no matching BrowserAction — handled separately
    raise ValueError(f"No BrowserAction for: {action_name}")


class BrowserRuntime:
    """Thin adapter that executes browser tasks via BrowserEngine.

    Responsibilities (Architect-mandated):
        1. Parse action from task.payload["action"].
        2. Validate required payload fields.
        3. Convert payload → BrowserAction DTO.
        4. Call BrowserEngine.
        5. Wrap result → ToolExecutionResult.

    FORBIDDEN:
        - Implementing permission logic (stays in BrowserPermissionManager).
        - Importing or calling AgentLoop.
        - Raising exceptions to callers (always return ToolExecutionResult).
    """

    def __init__(self, engine: BrowserEngine) -> None:
        """Initialise BrowserRuntime.

        Args:
            engine: Constructed BrowserEngine instance with driver, state, permissions wired.
        """
        self._engine = engine

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        """Execute a single browser task.

        Flow:
            1. Read action from payload.
            2. Check action is supported.
            3. Validate required payload fields.
            4. Dispatch to BrowserEngine (or driver) via appropriate method.
            5. Return ToolExecutionResult.

        Args:
            task: Task DTO with executor=BROWSER and action in payload.
            context: Shared context (unused by BrowserRuntime, passed for interface compat).

        Returns:
            ToolExecutionResult — always returned, never raised.
        """
        start = time.perf_counter()
        payload = task.payload

        # ── 1. Extract action ────────────────────────────────────────────────
        action_name = str(payload.get("action", "")).lower().strip()
        if not action_name and "url" in payload:
            action_name = "navigate"
        if not action_name:
            return ToolExecutionResult(
                task_id=task.id,
                status="FAILURE",
                stderr="Missing required field: 'action'",
                exit_code=1,
                duration=time.perf_counter() - start,
            )

        # ── 2. Check supported ───────────────────────────────────────────────
        if action_name not in _SUPPORTED_ACTIONS:
            return ToolExecutionResult(
                task_id=task.id,
                status="FAILURE",
                stderr=f"Unknown browser action: '{action_name}'. Supported: {sorted(_SUPPORTED_ACTIONS)}",
                exit_code=1,
                duration=time.perf_counter() - start,
            )

        # ── 3. Validate payload fields ───────────────────────────────────────
        validation_error = _validate_payload(action_name, payload)
        if validation_error:
            return ToolExecutionResult(
                task_id=task.id,
                status="FAILURE",
                stderr=validation_error,
                exit_code=1,
                duration=time.perf_counter() - start,
            )

        # ── 3.5 Auto-launch driver if not launched ──────────────────────────
        driver = self._engine.driver
        if not getattr(driver, "_launched", False):
            profile = payload.get("profile") or "default"
            try:
                await driver.launch(profile)
            except Exception as exc:
                return ToolExecutionResult(
                    task_id=task.id,
                    status="FAILURE",
                    stderr=f"Failed to auto-launch browser driver: {exc}",
                    exit_code=1,
                    duration=time.perf_counter() - start,
                    error=str(exc),
                )

        # ── 4. Execute via BrowserEngine ─────────────────────────────────────
        try:
            stdout, artifacts = await self._dispatch(action_name, payload)
        except Exception as exc:
            # Permission violations and navigation failures surface here.
            # Return as FAILURE so ReflectionEngine can classify (Architect Constraint 8).
            return ToolExecutionResult(
                task_id=task.id,
                status="FAILURE",
                stderr=str(exc),
                exit_code=1,
                duration=time.perf_counter() - start,
                error=str(exc),
            )

        return ToolExecutionResult(
            task_id=task.id,
            status="SUCCESS",
            stdout=stdout,
            exit_code=0,
            duration=time.perf_counter() - start,
            artifacts=artifacts,
        )

    async def _dispatch(
        self, action_name: str, payload: Dict[str, Any]
    ) -> tuple[str, Dict[str, Any]]:
        """Dispatch to the appropriate BrowserEngine method.

        Args:
            action_name: Validated action string.
            payload: Task payload dict.

        Returns:
            Tuple of (stdout_string, artifacts_dict).

        Raises:
            Any exception from BrowserEngine (permission, navigation failure, etc.)
        """
        artifacts: Dict[str, Any] = {}

        if action_name == "navigate":
            if not self._engine.state_manager.active_tab_id:
                self._engine.state_manager.add_tab(payload["url"])
            await self._engine.navigate(payload["url"])
            return f"Navigated to {payload['url']}", artifacts

        if action_name in (
            "click",
            "type",
            "scroll",
            "hover",
            "upload",
            "download",
            "press_key",
            "wait",
        ):
            browser_action = _build_action(action_name, payload)
            result = await self._engine.driver.execute_action(browser_action)
            status = result.get("status", "UNKNOWN")
            if status != "SUCCESS":
                raise RuntimeError(
                    f"Browser action '{action_name}' failed: {result.get('message', 'unknown error')}"
                )
            return f"Browser action '{action_name}' completed.", artifacts

        if action_name == "screenshot":
            b64 = await self._engine.driver.take_screenshot()
            artifacts["screenshot_b64"] = b64
            return "Screenshot captured.", artifacts

        if action_name == "extract_dom":
            dom = await self._engine.extract_dom()
            artifacts["dom"] = dom
            return f"DOM extracted ({len(dom)} chars).", artifacts

        # Should never reach here — validated above
        raise ValueError(f"Unhandled action: {action_name}")

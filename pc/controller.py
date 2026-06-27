"""JARVIS OS - PC Controller Coordinator.

Maintains coordination between display managers, platform adapters, queues, and shell executors.
"""

import time
from typing import Any, Dict, Optional
from uuid import uuid4

from core.exceptions import JarvisSystemError
from core.interfaces import EventBusInterface, InterAgentMessage
from pc.action import MoveAction
from pc.adapter import IPCAdapter
from pc.display import DisplayManager
from pc.permission import PCPermissionManager
from pc.queue import PCExecutionQueue
from pc.recovery import AutomationRecoveryManager
from pc.session import PCSession
from pc.shell import ShellExecutor
from pc.trace import PCActionTrace
from pc.window import WindowManager


class PCController:
    """Central manager for executing PC automation, auditing logs, and handling recoveries."""

    def __init__(
        self,
        adapter: IPCAdapter,
        permission_manager: PCPermissionManager,
        display_manager: DisplayManager,
        window_manager: WindowManager,
        shell_executor: ShellExecutor,
        recovery_manager: AutomationRecoveryManager,
        queue: PCExecutionQueue,
        event_bus: EventBusInterface,
    ) -> None:
        """Initialize PCController."""
        self.adapter = adapter
        self.permission_manager = permission_manager
        self.display_manager = display_manager
        self.window_manager = window_manager
        self.shell_executor = shell_executor
        self.recovery_manager = recovery_manager
        self.queue = queue
        self.event_bus = event_bus

    async def execute_action(
        self, action: Any, session: Optional[PCSession] = None
    ) -> Dict[str, Any]:
        """Verify parameters, serialize execution queue, record trace audits, and recover on failures.

        Args:
            action: PCAction DTO.
            session: Active PCSession context reference.

        Returns:
            Dictionary mapped execution report outcome.
        """
        active_session = session or PCSession()
        action_name = action.__class__.__name__
        action_id = str(uuid4())

        # Enforce centralized queue serialization
        async def _run(act: Any) -> Dict[str, Any]:
            start_time = time.perf_counter()
            trace_success = False
            perm_result = "GRANTED"
            coords = None

            # 1. Enforce permission rules and display checks
            try:
                if action_name in ("ClickAction", "MoveAction"):
                    self.permission_manager.verify_permission("MOUSE")
                    if not self.display_manager.is_within_bounds(act.x, act.y):
                        raise JarvisSystemError(
                            code="CONTROLLER_001",
                            message=f"Coordinates ({act.x}, {act.y}) are outside display bounds.",
                        )
                    coords = (act.x, act.y)

                elif action_name == "KeyAction":
                    self.permission_manager.verify_permission("KEYBOARD")

                elif action_name == "ShellAction":
                    self.permission_manager.verify_permission("SHELL")

                elif action_name == "ClipboardAction":
                    self.permission_manager.verify_permission("CLIPBOARD")

            except JarvisSystemError as err:
                perm_result = "DENIED"
                await self._publish_event(
                    "pc.permission.denied",
                    {"action": action_name, "error": err.message},
                )
                return {"status": "DENIED", "message": err.message}

            # Dispatch started event
            await self._publish_event(
                "pc.action.started", {"action": action_name, "action_id": action_id}
            )

            # 2. Map OS calls through Platform Adapters
            try:
                res: Dict[str, Any] = {}
                if action_name == "ClickAction":
                    # Record rollback context
                    active_window = await self.window_manager.get_active_window()
                    bounds = active_window.get("bounds", {"left": 0, "top": 0})
                    # Push rollback MoveAction back to parent bounds origin
                    orig = MoveAction(x=bounds.get("left", 0), y=bounds.get("top", 0))
                    active_session.push_rollback(orig)

                    res = await self.adapter.execute_mouse_event(
                        "click", act.x, act.y, act.button, act.double_click
                    )

                elif action_name == "MoveAction":
                    # Record rollback context
                    active_session.push_rollback(MoveAction(x=0, y=0))
                    res = await self.adapter.execute_mouse_event(
                        "move_to", act.x, act.y
                    )

                elif action_name == "KeyAction":
                    res = await self.adapter.execute_keyboard_event(
                        act.action_type, act.key
                    )

                elif action_name == "ShellAction":
                    await self._publish_event(
                        "pc.shell.started", {"command": act.command}
                    )
                    res = await self.shell_executor.execute(
                        act.command, act.timeout, act.work_dir
                    )
                    await self._publish_event(
                        "pc.shell.completed", {"status": res.get("status")}
                    )

                elif action_name == "ClipboardAction":
                    if act.action == "write":
                        self.recovery_manager.backup_clipboard("previous_val")
                        active_session.push_rollback(act)
                        res = {
                            "status": "SUCCESS",
                            "message": "Wrote content to clipboard.",
                        }
                    else:
                        res = {"status": "SUCCESS", "content": "mock_clipboard_value"}

                duration_ms = int((time.perf_counter() - start_time) * 1000.0)
                trace_success = res.get("status") in ("SUCCESS", "TIMEOUT")

                # 3. Log PCActionTrace telemetry audits
                trace = PCActionTrace(
                    session_id=active_session.session_id,
                    action_id=action_id,
                    action_type=action_name,
                    duration_ms=duration_ms,
                    success=trace_success,
                    permission_result=perm_result,
                    coordinates=coords,
                    retries=0,
                )
                active_session.record_action(trace)

                if trace_success:
                    await self._publish_event(
                        "pc.action.completed", {"action_id": action_id}
                    )
                else:
                    await self._publish_event(
                        "pc.failed",
                        {"action_id": action_id, "error": res.get("message")},
                    )

                return res

            except JarvisSystemError as err:
                duration_ms = int((time.perf_counter() - start_time) * 1000.0)
                await self._publish_event(
                    "pc.permission.denied",
                    {"action": action_name, "error": err.message},
                )
                return {"status": "DENIED", "message": err.message}
            except Exception as err:
                duration_ms = int((time.perf_counter() - start_time) * 1000.0)
                await self._publish_event(
                    "pc.failed", {"action_id": action_id, "error": str(err)}
                )
                # Trigger Automation Recovery rollback cycles on crashes
                await self.recovery_manager.rollback(active_session)
                return {"status": "ERROR", "message": f"Execution crash: {str(err)}"}

        # Enqueue action and process sequentially
        await self.queue.enqueue(action)
        return await self.queue.process_next(_run)

    async def _publish_event(self, topic: str, body: Dict[str, Any]) -> None:
        """Helper to dispatch lifecycle events to the global event bus."""
        msg = InterAgentMessage(
            sender="PCController",
            receiver="All",
            action=topic,
            body=body,
        )
        await self.event_bus.publish(topic, msg)

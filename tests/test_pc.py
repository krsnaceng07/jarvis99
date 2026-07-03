"""JARVIS OS - PC Controller Unit and Integration Tests.

Validates platform adapters, display bounds, window focuses, permissions, traces, recovery managers, queues, dry runs, sandboxed shells, and API routers.
"""

from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.exceptions import JarvisSystemError
from core.interfaces import EventBusInterface, InterAgentMessage
from pc.action import ClickAction, ClipboardAction, KeyAction, MoveAction, ShellAction
from pc.adapter import MockAdapter, WindowsAdapter
from pc.controller import PCController
from pc.display import DisplayManager
from pc.dryrun import DryRunExecutor
from pc.permission import PCPermissionManager
from pc.queue import PCExecutionQueue
from pc.recovery import AutomationRecoveryManager
from pc.routes import router, set_routing_context
from pc.session import PCSession
from pc.shell import ShellExecutor
from pc.trace import PCActionTrace
from pc.window import WindowManager


class MockEventBus(EventBusInterface):
    """Mock event bus for capturing published messages."""

    def __init__(self) -> None:
        """Initialize MockEventBus."""
        self.published_events: List[Dict[str, Any]] = []

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def publish(self, topic: str, message: InterAgentMessage) -> bool:
        self.published_events.append({"topic": topic, "message": message})
        return True

    async def subscribe(self, topic: str, callback: Any) -> str:
        return "mock_sub_id"


@pytest.fixture
def pc_setup() -> Dict[str, Any]:
    """Helper fixture initializing the PC Controller component dependencies."""
    adapter = MockAdapter()
    permission_manager = PCPermissionManager()
    display_manager = DisplayManager()
    window_manager = WindowManager(adapter)
    shell_executor = ShellExecutor()
    recovery_manager = AutomationRecoveryManager(adapter)
    queue = PCExecutionQueue()
    event_bus = MockEventBus()

    controller = PCController(
        adapter=adapter,
        permission_manager=permission_manager,
        display_manager=display_manager,
        window_manager=window_manager,
        shell_executor=shell_executor,
        recovery_manager=recovery_manager,
        queue=queue,
        event_bus=event_bus,
    )

    dryrun = DryRunExecutor(permission_manager, display_manager)

    return {
        "adapter": adapter,
        "permission_manager": permission_manager,
        "display_manager": display_manager,
        "window_manager": window_manager,
        "shell_executor": shell_executor,
        "recovery_manager": recovery_manager,
        "queue": queue,
        "event_bus": event_bus,
        "controller": controller,
        "dryrun": dryrun,
    }


@pytest.mark.asyncio
async def test_display_manager(pc_setup: Dict[str, Any]) -> None:
    """Verify display boundaries and coordinate mappings."""
    dm = pc_setup["display_manager"]

    # Bounds check
    assert dm.is_within_bounds(100, 100)
    assert not dm.is_within_bounds(2000, 2000)

    # Resolution translation mappings
    x, y = dm.map_to_primary(100, 100)
    assert x == 100 and y == 100

    info = dm.get_display_info()
    assert info["primary"]["width"] == 1920


@pytest.mark.asyncio
async def test_adapters_simulation(pc_setup: Dict[str, Any]) -> None:
    """Verify WindowsAdapter and MockAdapter simulations."""
    mock = pc_setup["adapter"]
    win = WindowsAdapter()

    # Mock Mouse Click
    res = await mock.execute_mouse_event("click", 100, 200)
    assert res["status"] == "SUCCESS"
    assert mock.cursor_pos == (100, 200)

    # Windows Keyboard Down/Up
    res = await win.execute_keyboard_event("down", "ctrl")
    assert res["status"] == "SUCCESS"
    assert "ctrl" in win.held_keys

    await win.execute_keyboard_event("up", "ctrl")
    assert "ctrl" not in win.held_keys

    # Active Window details
    win_info = await mock.get_active_window()
    assert win_info["title"] == "Mock Active Window"


@pytest.mark.asyncio
async def test_window_manager(pc_setup: Dict[str, Any]) -> None:
    """Verify WindowManager handles and titles filtering."""
    wm = pc_setup["window_manager"]

    # Focus and frontwards
    assert await wm.focus_window(1234)
    assert await wm.bring_to_front(1234)

    with pytest.raises(JarvisSystemError) as exc:
        await wm.focus_window(-1)
    assert "Invalid window handle" in exc.value.message

    with pytest.raises(JarvisSystemError) as exc:
        await wm.bring_to_front(-1)
    assert "Invalid window handle" in exc.value.message

    # Title filter match
    wins = await wm.find_windows_by_title("chrome")
    assert len(wins) == 1
    assert wins[0]["handle"] == 111111


@pytest.mark.asyncio
async def test_permission_gates(pc_setup: Dict[str, Any]) -> None:
    """Verify permission gates validation checks."""
    pm = pc_setup["permission_manager"]

    pm.verify_permission("SHELL")
    with pytest.raises(JarvisSystemError) as exc:
        pm.verify_permission("INVALID_PERM")
    assert "denied" in exc.value.message


@pytest.mark.asyncio
async def test_automation_session(pc_setup: Dict[str, Any]) -> None:
    """Verify session tracking, rollback stacks, and history registries."""
    session = PCSession()
    assert len(session.session_id) > 10

    # Rollback Stack
    session.push_rollback("revert_step_1")
    assert len(session.rollback_stack) == 1

    item = session.pop_rollback()
    assert item == "revert_step_1"
    assert session.pop_rollback() is None

    # History register
    trace = PCActionTrace(
        session_id=session.session_id,
        action_id="action-1",
        action_type="ClickAction",
        duration_ms=10,
        success=True,
        retries=0,
        permission_result="GRANTED",
        coordinates=None,
    )
    session.record_action(trace)
    assert len(session.action_history) == 1


@pytest.mark.asyncio
async def test_shell_executor() -> None:
    """Verify sandboxed command executions and output limits."""
    executor = ShellExecutor()

    # Allowed safe echo command
    res = await executor.execute("echo hello")
    assert res["status"] == "SUCCESS"
    assert "hello" in res["stdout"]

    # Blocked shell command
    with pytest.raises(JarvisSystemError) as exc:
        await executor.execute("rm -rf /")
    assert "restricted" in exc.value.message

    # Blocked working directories
    with pytest.raises(JarvisSystemError) as exc:
        await executor.execute("echo hello", work_dir="C:/Windows/System32")
    assert "blocked" in exc.value.message


@pytest.mark.asyncio
async def test_recovery_strategy(pc_setup: Dict[str, Any]) -> None:
    """Verify recovery key releases and rollback operations."""
    recovery = pc_setup["recovery_manager"]
    adapter = pc_setup["adapter"]
    session = PCSession()

    # Stuck keys release
    adapter.held_keys.add("shift")
    await recovery.release_keys(adapter.held_keys)
    assert "shift" not in adapter.held_keys

    # State Rollback
    session.push_rollback(MoveAction(x=10, y=20))
    await recovery.rollback(session)
    assert adapter.cursor_pos == (10, 20)


@pytest.mark.asyncio
async def test_execution_queue() -> None:
    """Verify execution queue FIFO serializations and pauses."""
    queue = PCExecutionQueue()
    assert queue.size == 0

    await queue.enqueue("Action A")
    await queue.enqueue("Action B")
    await queue.enqueue("Priority Action", priority=True)
    assert queue.size == 3

    # Callback list
    processed = []

    async def cb(action: Any) -> Dict[str, Any]:
        processed.append(action)
        return {"status": "SUCCESS"}

    # Process priority item first
    res = await queue.process_next(cb)
    assert res["status"] == "SUCCESS"
    assert processed[0] == "Priority Action"

    # Pause queue
    queue.pause()
    res = await queue.process_next(cb)
    assert res["status"] == "SKIPPED"

    # Resume queue
    queue.resume()
    await queue.process_next(cb)
    assert processed[1] == "Action A"

    # Cancel remaining
    queue.cancel_all()
    assert queue.size == 0


@pytest.mark.asyncio
async def test_dryrun_executor(pc_setup: Dict[str, Any]) -> None:
    """Verify simulation DryRun validations."""
    dryrun = pc_setup["dryrun"]

    # Click/Move validations
    res = await dryrun.validate_action(ClickAction(x=100, y=200))
    assert res["dry_run"] and res["valid"]

    # Bounds coordinate error
    with pytest.raises(JarvisSystemError) as exc:
        await dryrun.validate_action(ClickAction(x=3000, y=3000))
    assert "outside active monitor boundaries" in exc.value.message

    # Keyboard validation
    res = await dryrun.validate_action(KeyAction(key="a"))
    assert res["valid"]

    # Shell validation
    res = await dryrun.validate_action(ShellAction(command="echo hi"))
    assert res["valid"]

    with pytest.raises(JarvisSystemError) as exc:
        await dryrun.validate_action(ShellAction(command="rm -rf /"))
    assert "restricted" in exc.value.message

    # Clipboard validation
    res = await dryrun.validate_action(ClipboardAction(action="read"))
    assert res["valid"]


@pytest.mark.asyncio
async def test_pc_controller_flow(pc_setup: Dict[str, Any]) -> None:
    """Verify controller orchestrates adapters and trace telemetry logs."""
    controller = pc_setup["controller"]
    event_bus = pc_setup["event_bus"]

    # 1. Mouse MoveAction
    res = await controller.execute_action(MoveAction(x=150, y=250))
    assert res["status"] == "SUCCESS"
    assert len(event_bus.published_events) == 2
    assert event_bus.published_events[0]["topic"] == "pc.action.started"
    assert event_bus.published_events[1]["topic"] == "pc.action.completed"

    # 2. Keyboard KeyAction
    res = await controller.execute_action(KeyAction(key="enter", action_type="press"))
    assert res["status"] == "SUCCESS"

    # 3. ShellAction allowed
    res = await controller.execute_action(ShellAction(command="echo hi"))
    assert res["status"] == "SUCCESS"

    # 4. ClipboardAction write
    res = await controller.execute_action(ClipboardAction(action="write", content="hi"))
    assert res["status"] == "SUCCESS"

    # 5. Permission denied test
    controller.permission_manager.allowed_permissions.remove("MOUSE")
    res = await controller.execute_action(MoveAction(x=10, y=20))
    assert res["status"] == "DENIED"
    controller.permission_manager.allowed_permissions.add("MOUSE")

    # 6. Out of bounds test
    res = await controller.execute_action(MoveAction(x=3000, y=3000))
    assert res["status"] == "DENIED"

    # 7. Execution crash recovery test
    class CrashingAdapter(MockAdapter):
        async def execute_mouse_event(
            self, *args: Any, **kwargs: Any
        ) -> Dict[str, Any]:
            raise RuntimeError("Hardware failure")

    controller.adapter = CrashingAdapter()
    res = await controller.execute_action(MoveAction(x=10, y=20))
    assert res["status"] == "ERROR"
    assert "crash" in res["message"]


def test_api_routes(pc_setup: Dict[str, Any]) -> None:
    """Verify REST API endpoint adapters."""
    controller = pc_setup["controller"]
    set_routing_context(controller)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # Click Action
    res = client.post(
        "/api/v1/pc/action", json={"action_type": "click", "x": 10, "y": 20}
    )
    assert res.status_code == 200

    # MoveTo Action
    res = client.post(
        "/api/v1/pc/action", json={"action_type": "move_to", "x": 10, "y": 20}
    )
    assert res.status_code == 200

    # KeyPress Action
    res = client.post(
        "/api/v1/pc/action", json={"action_type": "key_press", "key": "enter"}
    )
    assert res.status_code == 200

    # Clipboard Write Action
    res = client.post(
        "/api/v1/pc/action", json={"action_type": "clipboard_write", "text": "hello"}
    )
    assert res.status_code == 200

    # Shell Exec Action
    res = client.post("/api/v1/pc/shell", json={"command": "echo hello"})
    assert res.status_code == 200


def test_api_routes_errors(pc_setup: Dict[str, Any]) -> None:
    """Verify endpoint error codes (400, 403, 503)."""
    controller = pc_setup["controller"]
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # 1. Uninitialized 503
    set_routing_context(None)  # type: ignore
    res = client.post(
        "/api/v1/pc/action", json={"action_type": "key_press", "key": "a"}
    )
    assert res.status_code == 503

    # Set initialized
    set_routing_context(controller)

    # 2. Coordinates missing on click 400
    res = client.post("/api/v1/pc/action", json={"action_type": "click"})
    assert res.status_code == 400

    # 3. Coordinates missing on move_to 400
    res = client.post("/api/v1/pc/action", json={"action_type": "move_to"})
    assert res.status_code == 400

    # 4. Key missing 400
    res = client.post("/api/v1/pc/action", json={"action_type": "key_press"})
    assert res.status_code == 400

    # 5. Clipboard text missing 400
    res = client.post("/api/v1/pc/action", json={"action_type": "clipboard_write"})
    assert res.status_code == 400

    # 6. Unsupported action category 400
    res = client.post("/api/v1/pc/action", json={"action_type": "unsupported_type"})
    assert res.status_code == 400

    # 7. Security block 403 (for restricted shell command)
    res = client.post("/api/v1/pc/shell", json={"command": "rm -rf /"})
    assert res.status_code == 403

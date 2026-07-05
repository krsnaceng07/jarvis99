"""Phase 25 — BrowserRuntime unit tests.

Validates:
    - All 9 action types (navigate, click, type, scroll, hover, upload, download, press_key, wait)
    - screenshot and extract_dom special actions
    - Missing action field → FAILURE
    - Unknown action → FAILURE (never raises)
    - Missing required payload fields → FAILURE
    - Permission denial flows through as FAILURE (Architect Constraint 5, 8)
    - BrowserEngine integration with MockCDPDriver
"""

from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

import pytest

from core.browser.driver import MockCDPDriver
from core.browser.engine import BrowserEngine
from core.browser.permission import BrowserPermissionManager
from core.browser.profile import BrowserContextManager, BrowserProfileManager
from core.browser.state import BrowserStateManager
from core.interfaces import EventBusInterface, InterAgentMessage
from core.reasoning.task import ExecutorType, Task
from core.tools.browser_runtime import BrowserRuntime

# ── Fixtures ─────────────────────────────────────────────────────────────────


class _MockEventBus(EventBusInterface):
    async def initialize(self) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def shutdown(self) -> None: ...

    async def publish(self, topic: str, message: InterAgentMessage) -> bool:
        return True

    async def subscribe(self, topic: str, callback: Any) -> str:
        return ""


def _make_engine() -> BrowserEngine:
    driver = MockCDPDriver()
    return BrowserEngine(
        driver=driver,
        state_manager=BrowserStateManager(),
        permission_manager=BrowserPermissionManager(),
        profile_manager=BrowserProfileManager(),
        context_manager=BrowserContextManager(BrowserProfileManager()),
        event_bus=_MockEventBus(),
    )


def _task(payload: Dict[str, Any]) -> Task:
    return Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.BROWSER,
        task_type="command",
        payload=payload,
    )


@pytest.fixture
async def runtime() -> BrowserRuntime:
    engine = _make_engine()
    # Pre-launch driver so action dispatching works
    await engine.driver.launch("Testing")
    return BrowserRuntime(engine)


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_navigate_success(runtime: BrowserRuntime) -> None:
    """Navigate action returns SUCCESS with the target URL in stdout."""
    task = _task({"action": "navigate", "url": "https://google.com"})
    result = await runtime.execute(task, {})
    assert result.status == "SUCCESS"
    assert "google.com" in result.stdout


@pytest.mark.asyncio
async def test_click_success(runtime: BrowserRuntime) -> None:
    task = _task({"action": "click", "selector": "#submit"})
    result = await runtime.execute(task, {})
    assert result.status == "SUCCESS"
    assert "click" in result.stdout.lower()


@pytest.mark.asyncio
async def test_type_success(runtime: BrowserRuntime) -> None:
    task = _task({"action": "type", "selector": "input", "text": "hello"})
    result = await runtime.execute(task, {})
    assert result.status == "SUCCESS"


@pytest.mark.asyncio
async def test_scroll_success(runtime: BrowserRuntime) -> None:
    task = _task({"action": "scroll", "direction": "down", "amount": 300})
    result = await runtime.execute(task, {})
    assert result.status == "SUCCESS"


@pytest.mark.asyncio
async def test_hover_success(runtime: BrowserRuntime) -> None:
    task = _task({"action": "hover", "selector": ".menu-item"})
    result = await runtime.execute(task, {})
    assert result.status == "SUCCESS"


@pytest.mark.asyncio
async def test_upload_success(runtime: BrowserRuntime) -> None:
    task = _task(
        {
            "action": "upload",
            "selector": "input[type=file]",
            "file_path": "/tmp/test.txt",
        }
    )
    result = await runtime.execute(task, {})
    assert result.status == "SUCCESS"


@pytest.mark.asyncio
async def test_download_success(runtime: BrowserRuntime) -> None:
    task = _task({"action": "download", "url": "https://google.com/file.pdf"})
    result = await runtime.execute(task, {})
    assert result.status == "SUCCESS"


@pytest.mark.asyncio
async def test_press_key_success(runtime: BrowserRuntime) -> None:
    task = _task({"action": "press_key", "key": "Enter"})
    result = await runtime.execute(task, {})
    assert result.status == "SUCCESS"


@pytest.mark.asyncio
async def test_wait_success(runtime: BrowserRuntime) -> None:
    task = _task({"action": "wait", "seconds_or_selector": 0.01})
    result = await runtime.execute(task, {})
    assert result.status == "SUCCESS"


@pytest.mark.asyncio
async def test_screenshot_returns_artifact(runtime: BrowserRuntime) -> None:
    task = _task({"action": "screenshot"})
    result = await runtime.execute(task, {})
    assert result.status == "SUCCESS"
    assert "screenshot_b64" in result.artifacts


@pytest.mark.asyncio
async def test_extract_dom_returns_artifact(runtime: BrowserRuntime) -> None:
    task = _task({"action": "extract_dom"})
    result = await runtime.execute(task, {})
    assert result.status == "SUCCESS"
    assert "dom" in result.artifacts
    assert "html" in result.artifacts["dom"].lower()


@pytest.mark.asyncio
async def test_missing_action_field(runtime: BrowserRuntime) -> None:
    """Payload without 'action' and without 'url' → structured FAILURE."""
    task = _task({"selector": ".btn"})
    result = await runtime.execute(task, {})
    assert result.status == "FAILURE"
    assert "action" in result.stderr.lower()


@pytest.mark.asyncio
async def test_legacy_url_fallback(runtime: BrowserRuntime) -> None:
    """Payload without 'action' but with 'url' defaults to 'navigate'."""
    task = _task({"url": "https://google.com"})
    result = await runtime.execute(task, {})
    assert result.status == "SUCCESS"
    assert "google.com" in result.stdout


@pytest.mark.asyncio
async def test_unknown_action(runtime: BrowserRuntime) -> None:
    """Unknown action → structured FAILURE, never raises."""
    task = _task({"action": "teleport"})
    result = await runtime.execute(task, {})
    assert result.status == "FAILURE"
    assert "teleport" in result.stderr.lower()


@pytest.mark.asyncio
async def test_missing_required_fields(runtime: BrowserRuntime) -> None:
    """Click without selector → structured FAILURE with helpful message."""
    task = _task({"action": "click"})
    result = await runtime.execute(task, {})
    assert result.status == "FAILURE"
    assert "selector" in result.stderr


@pytest.mark.asyncio
async def test_permission_denial_returns_failure(runtime: BrowserRuntime) -> None:
    """Navigate to restricted domain → FAILURE (not raise), for Reflection pipeline."""
    task = _task({"action": "navigate", "url": "https://malicious-website.com"})
    result = await runtime.execute(task, {})
    assert result.status == "FAILURE"
    assert result.error is not None
    assert "restricted" in result.error.lower() or "restricted" in result.stderr.lower()


@pytest.mark.asyncio
async def test_duration_is_positive(runtime: BrowserRuntime) -> None:
    """Every result should have a non-negative duration."""
    task = _task({"action": "screenshot"})
    result = await runtime.execute(task, {})
    assert result.duration >= 0.0


@pytest.mark.asyncio
async def test_result_task_id_matches(runtime: BrowserRuntime) -> None:
    """ToolExecutionResult.task_id matches the input task.id."""
    task = _task({"action": "extract_dom"})
    result = await runtime.execute(task, {})
    assert result.task_id == task.id
